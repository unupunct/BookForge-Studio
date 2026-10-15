"""One-step 'New book from manuscript': pick a file, a kind of book and a template."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QProgressBar, QPushButton, QVBoxLayout)

from ...importers.base import ImportOptions
from ...services.import_service import FILE_FILTER, StagedImport, run_import
from ...services.project_service import PROFILES, NewBookSpec
from ...services.template_service import TemplateService
from ...workers.task import run_task
from .. import theme
from .import_dialog import ENCODINGS


class ManuscriptDialog(QDialog):
    def __init__(self, parent, templates: TemplateService, start_dir: str = "", initial_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("New book from manuscript")
        self.resize(660, 600)
        self.staged: StagedImport | None = None
        self.templates = templates
        self._start_dir = start_dir
        lay = QVBoxLayout(self)
        intro = QLabel("Choose your manuscript, the kind of book and a template. The book is created "
                       "ready to preview and export: chapters, poems, page numbers and front matter "
                       "follow the template.")
        intro.setWordWrap(True)
        theme.set_muted(intro)
        lay.addWidget(intro)
        row = QHBoxLayout()
        self.path = QLineEdit(initial_path)
        self.path.setAccessibleName("Manuscript file")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        form = QFormLayout()
        self.category = QComboBox()
        for p in PROFILES.values():
            self.category.addItem(p.label, p.key)
        self.template = QComboBox()
        for t in templates.list_templates():
            self.template.addItem(t["name"], t["key"])
        self.title = QLineEdit()
        self.title.setPlaceholderText("From the document, or type one")
        self.author = QLineEdit()
        self.author.setPlaceholderText("From the document, or type one")
        self.poetry = QComboBox()
        self.poetry.addItem("Detect poems automatically", "auto")
        self.poetry.addItem("The whole text is poetry", "always")
        self.poetry.addItem("No poetry (prose only)", "never")
        self.split = QComboBox()
        self.split.addItem("Heading 1 starts a chapter", 1)
        self.split.addItem("Heading 2 starts a chapter", 2)
        self.split.addItem("One single chapter", 0)
        self.keep = QCheckBox("Keep centring, indents and spacing that differ from the body text")
        self.keep.setChecked(True)
        self.encoding = QComboBox()
        for label, enc in ENCODINGS:
            self.encoding.addItem(label, enc)
        form.addRow("Kind of book", self.category)
        form.addRow("Template", self.template)
        form.addRow("Title", self.title)
        form.addRow("Author", self.author)
        form.addRow("Poetry", self.poetry)
        form.addRow("Chapters", self.split)
        form.addRow("Text encoding", self.encoding)
        form.addRow("", self.keep)
        lay.addLayout(form)
        self.category.currentIndexChanged.connect(self._category_changed)
        self.parse_btn = QPushButton("Read manuscript and show report")
        theme.accent_button(self.parse_btn)
        self.parse_btn.clicked.connect(self._parse)
        lay.addWidget(self.parse_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.report = QPlainTextEdit(readOnly=True)
        self.report.setAccessibleName("Import report")
        lay.addWidget(self.report, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.create_btn = self.buttons.addButton("Create book", QDialogButtonBox.AcceptRole)
        self.create_btn.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self._category_changed()
        if initial_path:
            self._parse()

    def _category_changed(self) -> None:
        p = PROFILES[self.category.currentData()]
        i = self.template.findData(p.template)
        if i >= 0:
            self.template.setCurrentIndex(i)

    def _browse(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Choose manuscript", self._start_dir, FILE_FILTER)
        if f:
            self.path.setText(f)
            self._parse()

    def options(self) -> ImportOptions:
        return ImportOptions(encoding=self.encoding.currentData(), split_level=self.split.currentData(),
                             poetry_mode=self.poetry.currentData(), keep_formatting=self.keep.isChecked(),
                             update_metadata=True)

    def _parse(self) -> None:
        p = self.path.text().strip().strip('"')
        if not p:
            return
        opts = self.options()
        self.create_btn.setEnabled(False)
        self.parse_btn.setEnabled(False)
        self.progress.show()
        self.report.setPlainText("Reading…")
        run_task(lambda ctx: run_import(Path(p), opts), self._done, self._failed)

    def _done(self, staged: StagedImport) -> None:
        self.progress.hide()
        self.parse_btn.setEnabled(True)
        self.staged = staged
        r = staged.result
        if r.title and not self.title.text():
            self.title.setText(r.title)
        if r.author and not self.author.text():
            self.author.setText(r.author)
        words = sum(len(b.plain_text().split()) for s in r.sections for b in s.blocks)
        self.report.setPlainText(f"{len(r.sections)} chapter(s), {words:,} words, "
                                 f"{len(staged.assets)} image(s).\n\n" + r.report.text())
        self.create_btn.setEnabled(True)

    def _failed(self, message: str, exc) -> None:
        self.progress.hide()
        self.parse_btn.setEnabled(True)
        self.staged = None
        self.report.setPlainText("Import failed:\n" + message)

    def spec(self) -> NewBookSpec:
        return NewBookSpec(title=self.title.text().strip(), author=self.author.text().strip(),
                           profile=self.category.currentData(), template=self.template.currentData(),
                           cover=True, toc=True)
