"""Import dialog: parse in the background, review the report, then add to the book."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout)

from ...importers.base import ImportFailure, ImportOptions
from ...services.import_service import FILE_FILTER, StagedImport, run_import
from ...workers.task import Task, run_task
from .. import theme

ENCODINGS = [("Detect automatically (UTF-8, BOM aware)", None), ("UTF-8", "utf-8"),
             ("UTF-8 with BOM", "utf-8-sig"), ("Windows-1250 (Central European)", "cp1250"),
             ("Windows-1252 (Western)", "cp1252"), ("ISO-8859-2", "iso-8859-2"),
             ("ISO-8859-1", "latin-1"), ("UTF-16", "utf-16")]


class ImportDialog(QDialog):
    def __init__(self, parent, start_dir: str = "", initial_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Import manuscript")
        self.resize(640, 560)
        self.staged: StagedImport | None = None
        self.options = ImportOptions()
        self._task: Task | None = None
        self._start_dir = start_dir
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.path = QLineEdit(initial_path)
        self.path.setPlaceholderText("DOCX, TXT, Markdown, HTML or PDF file")
        self.path.setAccessibleName("File to import")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        note = QLabel("The original file is never modified. A snapshot is kept in the project.")
        theme.set_muted(note)
        lay.addWidget(note)

        form = QFormLayout()
        self.split = QComboBox()
        self.split.addItem("Heading 1 starts a chapter", 1)
        self.split.addItem("Heading 2 starts a chapter", 2)
        self.split.addItem("Import as a single chapter", 0)
        self.encoding = QComboBox()
        for label, enc in ENCODINGS:
            self.encoding.addItem(label, enc)
        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText(r"Text files: regex for chapter lines (default: Chapter N, Capitolul N…)")
        self.detect = QCheckBox("Text files: use the first short line as the title")
        self.detect.setChecked(True)
        self.poetry = QCheckBox("Text files: keep line breaks (poetry)")
        self.meta = QCheckBox("Use the document title as the book title if still unset")
        self.meta.setChecked(True)
        form.addRow("Chapters", self.split)
        form.addRow("Text encoding", self.encoding)
        form.addRow("Chapter pattern", self.pattern)
        form.addRow("", self.detect)
        form.addRow("", self.poetry)
        form.addRow("", self.meta)
        lay.addLayout(form)

        self.parse_btn = QPushButton("Read file and show report")
        theme.accent_button(self.parse_btn)
        self.parse_btn.clicked.connect(self._parse)
        lay.addWidget(self.parse_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.report = QPlainTextEdit(readOnly=True)
        self.report.setPlaceholderText("The import report appears here: what was converted and what was not.")
        self.report.setAccessibleName("Import report")
        lay.addWidget(self.report, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.add_btn = self.buttons.addButton("Add to book", QDialogButtonBox.AcceptRole)
        self.add_btn.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        if initial_path:
            self._parse()

    def _browse(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Import manuscript", self._start_dir, FILE_FILTER)
        if p:
            self.path.setText(p)
            self._parse()

    def _collect(self) -> ImportOptions:
        return ImportOptions(
            encoding=self.encoding.currentData(), split_level=self.split.currentData(),
            chapter_pattern=self.pattern.text().strip() or None, detect_title=self.detect.isChecked(),
            preserve_line_breaks=self.poetry.isChecked(), update_metadata=self.meta.isChecked())

    def _parse(self) -> None:
        p = self.path.text().strip().strip('"')
        if not p:
            return
        self.options = self._collect()
        self.add_btn.setEnabled(False)
        self.progress.show()
        self.parse_btn.setEnabled(False)
        self.report.setPlainText("Reading…")
        opts = self.options
        self._task = run_task(lambda ctx: run_import(Path(p), opts), self._done, self._failed)

    def _done(self, staged: StagedImport) -> None:
        self.progress.hide()
        self.parse_btn.setEnabled(True)
        self.staged = staged
        rep = staged.result.report
        n_sec = len(staged.result.sections)
        words = sum(len(b.plain_text().split()) for s in staged.result.sections for b in s.blocks)
        head = f"{n_sec} chapter(s), {words:,} words, {len(staged.assets)} image(s) ready to add.\n\n"
        self.report.setPlainText(head + rep.text())
        self.add_btn.setEnabled(True)

    def _failed(self, message: str, exc) -> None:
        self.progress.hide()
        self.parse_btn.setEnabled(True)
        self.staged = None
        self.report.setPlainText("Import failed:\n" + message)
        self.add_btn.setEnabled(False)
