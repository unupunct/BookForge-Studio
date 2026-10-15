"""Guided new-book wizard."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
                               QWizard, QWizardPage)

from ...domain.layouts import PAGE_SIZES
from ...services.project_service import PROFILES, NewBookSpec
from ...services.template_service import TemplateService
from .. import theme

LANGUAGES = [("English", "en"), ("Română", "ro"), ("Français", "fr"), ("Deutsch", "de"),
             ("Español", "es"), ("Italiano", "it"), ("Português", "pt"),
             ("Magyar", "hu"), ("Polski", "pl")]


class _BasicsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("About your book")
        self.setSubTitle("Everything here can be changed later. Only the title is required.")
        form = QFormLayout(self)
        self.title = QLineEdit()
        self.title.setPlaceholderText("My Book")
        self.title.setAccessibleName("Book title")
        self.subtitle = QLineEdit()
        self.author = QLineEdit()
        self.language = QComboBox()
        for label, code in LANGUAGES:
            self.language.addItem(f"{label} ({code})", code)
        form.addRow("Title *", self.title)
        form.addRow("Subtitle", self.subtitle)
        form.addRow("Author", self.author)
        form.addRow("Language", self.language)
        self.registerField("title*", self.title)

    def isComplete(self) -> bool:
        return bool(self.title.text().strip())


class _TypePage(QWizardPage):
    def __init__(self, templates: TemplateService):
        super().__init__()
        self.templates = templates
        self.setTitle("Kind of book")
        self.setSubTitle("The category chooses sensible defaults, never limits.")
        form = QFormLayout(self)
        self.category = QComboBox()
        for p in PROFILES.values():
            self.category.addItem(p.label, p.key)
        self.desc = QLabel()
        self.desc.setProperty("muted", True)
        self.desc.setWordWrap(True)
        self.output = QComboBox()
        self.output.addItem("Digital reading (PDF)", "digital")
        self.output.addItem("Print on paper", "print")
        self.output.addItem("Both digital and print", "both")
        self.template = QComboBox()
        for t in templates.list_templates():
            self.template.addItem(t["name"], t["key"])
        form.addRow("Category", self.category)
        form.addRow("", self.desc)
        form.addRow("Intended output", self.output)
        form.addRow("Starting template", self.template)
        self.category.currentIndexChanged.connect(self._changed)
        self._changed()

    def _changed(self) -> None:
        p = PROFILES[self.category.currentData()]
        self.desc.setText(p.description)
        i = self.template.findData(p.template)
        if i >= 0:
            self.template.setCurrentIndex(i)


class _LayoutPage(QWizardPage):
    def __init__(self, type_page: _TypePage):
        super().__init__()
        self.type_page = type_page
        self.setTitle("Page and structure")
        self.setSubTitle("Choose a page size, or keep the template's own.")
        form = QFormLayout(self)
        self.size = QComboBox()
        self.size.addItem("Template default", None)
        for name in PAGE_SIZES:
            self.size.addItem(name if name != "Custom" else "Custom (set later in Book properties)", name)
        self.cover = QCheckBox("Include front and back covers")
        self.cover.setChecked(True)
        self.toc = QCheckBox("Generate a table of contents")
        self.toc.setChecked(True)
        self.new_page = QCheckBox("Start every chapter on a new page")
        self.new_page.setChecked(True)
        form.addRow("Page size", self.size)
        form.addRow("", self.cover)
        form.addRow("", self.toc)
        form.addRow("", self.new_page)


class NewBookWizard(QWizard):
    def __init__(self, parent=None, templates: TemplateService | None = None):
        super().__init__(parent)
        self.setWindowTitle("New book")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.HaveFinishButtonOnEarlyPages, True)  # partial completion
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        templates = templates or TemplateService()
        self.basics = _BasicsPage()
        self.kind = _TypePage(templates)
        self.layout_page = _LayoutPage(self.kind)
        for p in (self.basics, self.kind, self.layout_page):
            self.addPage(p)
        self.setButtonText(QWizard.FinishButton, "Create book")
        self.resize(560, 460)

    def spec(self) -> NewBookSpec:
        return NewBookSpec(
            title=self.basics.title.text().strip() or "Untitled Book",
            subtitle=self.basics.subtitle.text().strip(), author=self.basics.author.text().strip(),
            language=self.basics.language.currentData(), profile=self.kind.category.currentData(),
            output=self.kind.output.currentData(), template=self.kind.template.currentData(),
            page_size=self.layout_page.size.currentData(), cover=self.layout_page.cover.isChecked(),
            toc=self.layout_page.toc.isChecked(),
            chapters_new_page=self.layout_page.new_page.isChecked())
