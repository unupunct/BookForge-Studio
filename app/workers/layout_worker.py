"""Debounced, single-flight background layout used by the preview and status bar."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QTimer, Signal

from ..domain.book import BookProject
from ..layout.model import LayoutResult
from ..layout.pagination import LayoutCancelled, LayoutEngine
from .task import Task


class LayoutController(QObject):
    layout_ready = Signal(object, int)  # LayoutResult, generation
    layout_failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, debounce_ms: int = 600, parent: QObject | None = None):
        super().__init__(parent)
        self.engine = LayoutEngine()
        self.generation = 0
        self._snapshot_source = None
        self._running: Task | None = None
        self._again = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._start)

    def bind(self, snapshot_fn) -> None:
        """snapshot_fn() -> BookProject copy, called on the GUI thread."""
        self._snapshot_source = snapshot_fn

    def request(self, immediate: bool = False) -> None:
        self.generation += 1
        if self._running is not None:
            self._again = True
            self._running.ctx.cancel()
            return
        if immediate:
            self._timer.stop()
            self._start()
        else:
            self._timer.start()

    def _start(self) -> None:
        if self._snapshot_source is None or self._running is not None:
            return
        book: BookProject = self._snapshot_source()
        gen = self.generation

        def work(ctx):
            return self.engine.build(book, ctx.cancelled)

        task = Task(work, "layout")
        task.signals.finished.connect(lambda res, g=gen: self._done(res, g))
        task.signals.failed.connect(self._failed)
        self._running = task
        self.busy_changed.emit(True)
        task.start()

    def _finish(self) -> None:
        self._running = None
        self.busy_changed.emit(False)
        if self._again:
            self._again = False
            self._timer.start()

    def _done(self, res: LayoutResult, gen: int) -> None:
        self._finish()
        if gen == self.generation:
            self.layout_ready.emit(res, gen)

    def _failed(self, message: str, exc) -> None:
        self._finish()
        if not isinstance(exc, LayoutCancelled):
            self.layout_failed.emit(message)

    def wait_idle(self, timeout_ms: int = 15000) -> None:
        """Test helper: spin the event loop until no layout is running or pending."""
        from PySide6.QtCore import QCoreApplication, QEventLoop
        import time
        end = time.time() + timeout_ms / 1000
        while time.time() < end and (self._running is not None or self._timer.isActive()
                                     or self._again):
            QCoreApplication.processEvents(QEventLoop.AllEvents, 20)
            time.sleep(0.005)
