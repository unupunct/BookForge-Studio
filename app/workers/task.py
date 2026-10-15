"""Background tasks with progress and cancellation (QThreadPool based)."""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class TaskContext:
    def __init__(self, emit_progress: Callable[[int, int], None]):
        self._cancel = threading.Event()
        self._emit = emit_progress

    def cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def progress(self, done: int, total: int) -> None:
        self._emit(done, total)


class _Signals(QObject):
    progress = Signal(int, int)
    finished = Signal(object)
    failed = Signal(str, object)


class Task(QRunnable):
    """Runs fn(ctx) on the global thread pool. Signals are delivered on the GUI thread."""

    def __init__(self, fn: Callable[[TaskContext], Any], label: str = ""):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.label = label
        self.signals = _Signals()
        self.ctx = TaskContext(lambda d, t: self.signals.progress.emit(d, t))

    def run(self) -> None:
        try:
            result = self.fn(self.ctx)
        except BaseException as e:  # noqa: BLE001 - reported to the UI, never swallowed
            self.signals.failed.emit(f"{type(e).__name__}: {e}" if not str(e) else str(e), e)
            if not isinstance(e, Exception):
                raise
            return
        self.signals.finished.emit(result)

    def start(self) -> "Task":
        QThreadPool.globalInstance().start(self)
        return self


def run_task(fn: Callable[[TaskContext], Any], on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[str, Any], None] | None = None,
             on_progress: Callable[[int, int], None] | None = None, label: str = "") -> Task:
    t = Task(fn, label)
    if on_done:
        t.signals.finished.connect(on_done)
    if on_error:
        t.signals.failed.connect(on_error)
    if on_progress:
        t.signals.progress.connect(on_progress)
    return t.start()
