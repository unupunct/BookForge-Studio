"""Export workflow dialog: validate, review issues, export in the background, verify."""
from __future__ import annotations

import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QProgressBar, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from ...application_state import AppState
from ...exporters.pdf_exporter import PROFILES
from ...layout.pagination import LayoutEngine
from ...services.export_service import (ExportError, ExportResult, export_other, export_pdf)
from ...services.validation_service import ValidationReport, validate_book
from ...workers.task import Task, run_task
from .. import theme

FORMATS = [("Digital PDF", "pdf:digital", ".pdf"), ("Print PDF (bleed, crop marks)", "pdf:print", ".pdf"),
           ("Proof PDF (boundaries and diagnostics)", "pdf:proof", ".pdf"),
           ("Word document (editable manuscript)", "docx", ".docx"), ("HTML (single file)", "html", ".html"),
           ("Markdown (structured text + images folder)", "markdown", ".md")]
SEV_COLOR = {"error": theme.ERROR, "warning": theme.WARNING, "info": theme.TEXT_MUTED}


def safe_filename(title: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(".")
    return s or "book"


class ExportDialog(QDialog):
    def __init__(self, state: AppState, parent=None, initial_format: str = "pdf:digital"):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Export")
        self.resize(680, 600)
        self._task: Task | None = None
        self._stage = "idle"  # idle | validating | review | exporting | done
        self._layout = None
        self._book = None
        self.result: ExportResult | None = None
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.format = QComboBox()
        for label, key, _ in FORMATS:
            self.format.addItem(label, key)
        self.format.setCurrentIndex(max(self.format.findData(initial_format), 0))
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setAccessibleName("Destination file")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.bleed = QDoubleSpinBox(minimum=0, maximum=10, singleStep=0.5, suffix=" mm",
                                    value=state.project.settings.bleed_mm)
        self.crop = QCheckBox("Crop marks")
        self.crop.setChecked(True)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        theme.set_muted(self.desc)
        self.overwrite = QCheckBox("Replace the file if it already exists")
        form.addRow("Format", self.format)
        form.addRow("", self.desc)
        form.addRow("File", row)
        form.addRow("", self.overwrite)
        form.addRow("Bleed", self.bleed)
        form.addRow("", self.crop)
        lay.addLayout(form)
        self.issues = QTreeWidget()
        self.issues.setHeaderLabels(["Severity", "Issue"])
        self.issues.setRootIsDecorated(False)
        self.issues.setColumnWidth(0, 90)
        self.issues.setAccessibleName("Validation issues")
        lay.addWidget(self.issues, 1)
        self.force = QCheckBox("Export despite the errors listed above")
        self.force.hide()
        lay.addWidget(self.force)
        self.progress = QProgressBar()
        self.progress.hide()
        lay.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        btns = QHBoxLayout()
        self.open_btn = QPushButton("Show in folder")
        self.open_btn.hide()
        self.go = QPushButton("Validate and export")
        theme.accent_button(self.go)
        self.cancel = QPushButton("Close")
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(self.go)
        btns.addWidget(self.cancel)
        lay.addLayout(btns)
        self.go.clicked.connect(self._go)
        self.cancel.clicked.connect(self._cancel)
        self.open_btn.clicked.connect(self._show_folder)
        self.format.currentIndexChanged.connect(self._format_changed)
        self._format_changed()

    # ------------------------------------------------------------------ helpers
    def _fmt(self) -> tuple[str, str]:
        key = self.format.currentData()
        ext = next(e for _, k, e in FORMATS if k == key)
        return key, ext

    def _format_changed(self) -> None:
        key, ext = self._fmt()
        is_print = key == "pdf:print"
        self.bleed.setEnabled(is_print)
        self.crop.setEnabled(is_print)
        if key.startswith("pdf:"):
            self.desc.setText(PROFILES[key[4:]].description)
        else:
            self.desc.setText({"docx": "Editable manuscript. Page layout and covers are simplified.",
                               "html": "One self-contained file with embedded images.",
                               "markdown": "Structured text. Images are written to a folder next to the file."}[key])
        if not self.path.text() or Path(self.path.text()).suffix in (".pdf", ".docx", ".html", ".md"):
            base = Path(self.path.text()).parent if self.path.text() else self._default_dir()
            self.path.setText(str(base / (safe_filename(self.state.project.metadata.title) + ext)))
        self._reset_stage()

    def _default_dir(self) -> Path:
        if self.state.path:
            return self.state.path.parent
        d = self.state.settings_store.data.last_export_dir
        return Path(d) if d and Path(d).exists() else Path.home() / "Documents"

    def _browse(self) -> None:
        key, ext = self._fmt()
        p, _ = QFileDialog.getSaveFileName(self, "Export to", self.path.text(),
                                           f"{ext.upper()[1:]} (*{ext})", options=QFileDialog.DontConfirmOverwrite)
        if p:
            self.path.setText(p)
            self._reset_stage()

    def _reset_stage(self) -> None:
        if self._stage in ("review", "done", "idle"):
            self._stage = "idle"
            self.go.setText("Validate and export")
            self.go.setEnabled(True)
            self.force.hide()
            self.open_btn.hide()

    # ------------------------------------------------------------------- workflow
    def _go(self) -> None:
        if self._stage == "idle":
            self._start_validation()
        elif self._stage == "review":
            if self._has_errors and not self.force.isChecked():
                self.status.setText("Fix the errors, or tick “Export despite the errors”.")
                return
            self._start_export()

    def _start_validation(self) -> None:
        dest = Path(self.path.text().strip().strip('"'))
        if not dest.name:
            self.status.setText("Choose a destination file.")
            return
        if dest.exists() and not self.overwrite.isChecked():
            r = QMessageBox.question(self, "File exists", f"'{dest.name}' already exists. Replace it?")
            if r != QMessageBox.Yes:
                self.status.setText("Choose another name or allow replacing the file.")
                return
            self.overwrite.setChecked(True)
        self.state.flush()
        self._book = self.state.project.snapshot()
        self._dest = dest
        key, _ = self._fmt()
        self._stage = "validating"
        self.go.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText("Step 1 of 2: laying out and validating the book…")
        self.issues.clear()
        book, profile = self._book, key[4:] if key.startswith("pdf:") else "digital"

        def work(ctx):
            layout = LayoutEngine().build(book, ctx.cancelled)
            return layout, validate_book(book, layout, profile)
        self._task = run_task(work, self._validated, self._failed)

    def _validated(self, payload) -> None:
        self._layout, report = payload
        self._fill_issues(report)
        self.progress.hide()
        if report.errors or report.warnings:
            self._stage = "review"
            self.go.setEnabled(True)
            self.go.setText("Export now")
            self.force.setVisible(bool(report.errors))
            self.force.setChecked(False)
            self.status.setText(f"Review the issues ({report.summary()}), then choose Export now.")
        else:
            self._start_export()

    def _fill_issues(self, report: ValidationReport) -> None:
        self._has_errors = bool(report.errors)
        order = {"error": 0, "warning": 1, "info": 2}
        for i in sorted(report.issues, key=lambda x: order.get(x.severity, 3)):
            it = QTreeWidgetItem([i.severity.upper(), i.message +
                                  (f"  (page {i.page_index + 1})" if i.page_index is not None else "")])
            it.setForeground(0, QBrush(QColor(SEV_COLOR.get(i.severity, theme.TEXT))))
            self.issues.addTopLevelItem(it)

    def _start_export(self) -> None:
        key, _ = self._fmt()
        self._stage = "exporting"
        self.go.setEnabled(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("Step 2 of 2: writing and verifying the file…")
        self.cancel.setText("Cancel export")
        book, dest, layout = self._book, self._dest, self._layout
        overwrite = self.overwrite.isChecked()
        bleed, crop = self.bleed.value(), self.crop.isChecked()

        def work(ctx):
            if key.startswith("pdf:"):
                def prog(done, total):
                    ctx.progress(done, total)
                return export_pdf(book, dest, key[4:], overwrite=overwrite, allow_errors=True,
                                  layout=layout, bleed_mm=bleed if key == "pdf:print" else None,
                                  crop_marks=crop if key == "pdf:print" else None,
                                  progress=prog, cancel=ctx.cancelled)
            return export_other(book, dest, key, overwrite=overwrite)

        self._task = run_task(work, self._exported, self._failed,
                              on_progress=lambda d, t: (self.progress.setMaximum(max(t, 1)),
                                                        self.progress.setValue(d)))

    def _exported(self, res: ExportResult) -> None:
        self.result = res
        self._stage = "done"
        self.progress.hide()
        self.cancel.setText("Close")
        self.state.settings_store.data.last_export_dir = str(res.path.parent)
        self.state.settings_store.save()
        lines = [f"✔ {res.summary()}"]
        if res.preflight:
            p = res.preflight
            lines.append(f"Verified: {p['page_count']} pages, fonts embedded: "
                         f"{'yes' if p['all_fonts_embedded'] else 'no'}"
                         + (f", lowest image resolution {p['min_image_dpi']} dpi" if p.get("min_image_dpi") else ""))
        lines.extend(res.notes)
        self.status.setText("\n".join(lines))
        self.go.setEnabled(True)
        self.go.setText("Export again")
        self._stage = "idle"
        self.open_btn.show()

    def _failed(self, message: str, exc) -> None:
        self.progress.hide()
        self.cancel.setText("Close")
        self._stage = "idle"
        self.go.setEnabled(True)
        self.go.setText("Validate and export")
        self.status.setText("✖ " + message)

    def _cancel(self) -> None:
        if self._stage == "exporting" and self._task:
            self._task.ctx.cancel()
            self.status.setText("Cancelling…")
            return
        self.reject()

    def reject(self) -> None:
        if self._task and self._stage in ("validating", "exporting"):
            self._task.ctx.cancel()
        super().reject()

    def _show_folder(self) -> None:
        if self.result:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result.path.parent)))
