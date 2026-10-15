"""Export all formats in one go."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from ...application_state import AppState
from ...services.export_all import DEFAULT_KEYS, FORMATS, ExportAllItem, export_all, safe_name
from ...workers.task import Task, run_task
from .. import theme


class ExportAllDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Export all formats")
        self.resize(560, 560)
        self.results: list[ExportAllItem] = []
        self._task: Task | None = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        row = QHBoxLayout()
        start = state.path.parent if state.path else Path(state.settings_store.data.last_export_dir or Path.home() / "Documents")
        self.folder = QLineEdit(str(start))
        self.folder.setAccessibleName("Destination folder")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        self.base = QLineEdit(safe_name(state.project.metadata.title))
        self.sub = QCheckBox("Put the files in a new folder named after the book")
        self.sub.setChecked(True)
        self.overwrite = QCheckBox("Replace files that already exist")
        self.errors = QCheckBox("Export PDFs even if validation finds errors")
        form.addRow("Folder", row)
        form.addRow("File name", self.base)
        form.addRow("", self.sub)
        form.addRow("", self.overwrite)
        form.addRow("", self.errors)
        lay.addLayout(form)
        lay.addWidget(QLabel("Formats"))
        self.boxes: dict[str, QCheckBox] = {}
        for key, label, pattern in FORMATS:
            cb = QCheckBox(f"{label}   →   {pattern.format(b='…')}")
            cb.setChecked(key in DEFAULT_KEYS)
            self.boxes[key] = cb
            lay.addWidget(cb)
        self.progress = QProgressBar()
        self.progress.hide()
        lay.addWidget(self.progress)
        self.log = QPlainTextEdit(readOnly=True)
        self.log.setAccessibleName("Export results")
        lay.addWidget(self.log, 1)
        btns = QHBoxLayout()
        self.open_btn = QPushButton("Show in folder")
        self.open_btn.hide()
        self.go = QPushButton("Export")
        theme.accent_button(self.go)
        close = QPushButton("Close")
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(self.go)
        btns.addWidget(close)
        lay.addLayout(btns)
        self.go.clicked.connect(self.start_export)
        close.clicked.connect(self.reject)
        self.open_btn.clicked.connect(self._show)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Export to folder", self.folder.text())
        if d:
            self.folder.setText(d)

    def target_folder(self) -> Path:
        base = Path(self.folder.text().strip().strip('"'))
        if self.sub.isChecked():
            base = base / safe_name(self.base.text() or self.state.project.metadata.title)
        return base

    def start_export(self) -> None:
        keys = [k for k, cb in self.boxes.items() if cb.isChecked()]
        if not keys:
            self.log.setPlainText("Choose at least one format.")
            return
        target = self.target_folder()
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.log.setPlainText(f"Cannot create '{target}': {e}")
            return
        self.state.flush()
        book = self.state.project.snapshot()
        self.go.setEnabled(False)
        self.log.setPlainText("Working…")
        self.progress.setRange(0, len(keys))
        self.progress.setValue(0)
        self.progress.show()
        base, ow, errs = self.base.text() or None, self.overwrite.isChecked(), self.errors.isChecked()

        def work(ctx):
            return export_all(book, target, base, keys, overwrite=ow, allow_errors=errs,
                              progress=lambda d, t, label: ctx.progress(d, t), cancel=ctx.cancelled)
        self._target = target
        self._task = run_task(work, self._done, self._failed,
                              on_progress=lambda d, t: self.progress.setValue(d))

    def _done(self, results: list[ExportAllItem]) -> None:
        self.results = results
        self.progress.hide()
        self.go.setEnabled(True)
        lines = [("✔ " if r.ok else "✖ ") + r.label + ": " + r.message for r in results]
        ok = sum(1 for r in results if r.ok)
        lines.append(f"\n{ok} of {len(results)} exported to {self._target}")
        self.log.setPlainText("\n".join(lines))
        self.state.settings_store.data.last_export_dir = str(self._target.parent)
        self.state.settings_store.save()
        self.open_btn.setVisible(ok > 0)

    def _failed(self, message: str, exc) -> None:
        self.progress.hide()
        self.go.setEnabled(True)
        self.log.setPlainText("✖ " + message)

    def reject(self) -> None:
        if self._task:
            self._task.ctx.cancel()
        super().reject()

    def _show(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._target)))
