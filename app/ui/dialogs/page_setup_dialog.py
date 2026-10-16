"""Page setup for one section: its own page size, margins and number of columns."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QLabel, QSpinBox, QVBoxLayout)

from ...domain.layouts import PAGE_SIZES, BookSettings
from ...domain.page_setup import MAX_COLUMNS
from ...domain.sections import Section

MARGIN_KEYS = ("top", "bottom", "inner", "outer")


def describe_page(page: dict | None) -> str:
    """One line for the section panel: what this section changes compared with the book."""
    page = page or {}
    bits = []
    if int(page.get("columns", 1) or 1) > 1:
        bits.append(f"{int(page['columns'])} columns")
    if page.get("page_size") or page.get("width_mm"):
        bits.append("own page size")
    if page.get("margins"):
        bits.append("own margins")
    return ", ".join(bits) if bits else "Same as the book"


class SectionPageDialog(QDialog):
    def __init__(self, parent, section: Section, settings: BookSettings):
        super().__init__(parent)
        self.setWindowTitle(f"Page setup – {section.title or section.kind}")
        self.settings = settings
        page = section.page or {}
        lay = QVBoxLayout(self)
        intro = QLabel("These choices apply to this section and its sub-sections only. A change of page size or margins "
                       "starts the section on a new page. Everything left at the book setting follows the book.")
        intro.setWordWrap(True)
        intro.setProperty("muted", True)
        lay.addWidget(intro)

        size_box = QGroupBox("Page size")
        f1 = QFormLayout(size_box)
        self.size_choice = QComboBox()
        self.size_choice.addItem("Same as the book", "")
        for name in PAGE_SIZES:
            if name != "Custom":
                self.size_choice.addItem(name, name)
        self.size_choice.addItem("Custom size…", "custom")
        self.width_mm = QDoubleSpinBox(minimum=40, maximum=1000, decimals=1, suffix=" mm", value=settings.width_mm)
        self.height_mm = QDoubleSpinBox(minimum=40, maximum=1000, decimals=1, suffix=" mm", value=settings.height_mm)
        self.landscape = QCheckBox("Landscape")
        f1.addRow("Size", self.size_choice)
        f1.addRow("Width", self.width_mm)
        f1.addRow("Height", self.height_mm)
        f1.addRow("", self.landscape)
        lay.addWidget(size_box)

        margin_box = QGroupBox("Margins")
        f2 = QFormLayout(margin_box)
        self.own_margins = QCheckBox("Use margins of its own")
        f2.addRow("", self.own_margins)
        base = settings.margins
        self.margin = {}
        for key in MARGIN_KEYS:
            sp = QDoubleSpinBox(minimum=0, maximum=200, decimals=1, suffix=" mm", value=getattr(base, key))
            self.margin[key] = sp
            f2.addRow(key.capitalize(), sp)
        lay.addWidget(margin_box)

        col_box = QGroupBox("Columns")
        f3 = QFormLayout(col_box)
        self.columns = QSpinBox(minimum=1, maximum=MAX_COLUMNS, value=1)
        self.gap = QDoubleSpinBox(minimum=1, maximum=40, decimals=1, suffix=" mm", value=8.0)
        f3.addRow("Columns", self.columns)
        f3.addRow("Space between", self.gap)
        note = QLabel("The section title spans the page; the text below it runs in columns.")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        f3.addRow("", note)
        lay.addWidget(col_box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Reset).setText("Back to the book's setup")
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self._reset)
        lay.addWidget(buttons)

        # initial state from the section
        if page.get("page_size") in PAGE_SIZES and page.get("page_size") != "Custom":
            self.size_choice.setCurrentIndex(self.size_choice.findData(page["page_size"]))
        elif page.get("width_mm") and page.get("height_mm"):
            self.size_choice.setCurrentIndex(self.size_choice.findData("custom"))
            self.width_mm.setValue(float(page["width_mm"]))
            self.height_mm.setValue(float(page["height_mm"]))
        self.landscape.setChecked(bool(page.get("landscape")))
        if page.get("margins"):
            self.own_margins.setChecked(True)
            for k, v in page["margins"].items():
                if k in self.margin:
                    self.margin[k].setValue(float(v))
        self.columns.setValue(int(page.get("columns", 1) or 1))
        self.gap.setValue(float(page.get("column_gap_mm", 8.0) or 8.0))
        self.size_choice.currentIndexChanged.connect(self._sync)
        self.own_margins.toggled.connect(self._sync)
        self.columns.valueChanged.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        custom = self.size_choice.currentData() == "custom"
        self.width_mm.setEnabled(custom)
        self.height_mm.setEnabled(custom)
        self.landscape.setEnabled(bool(self.size_choice.currentData()))
        for sp in self.margin.values():
            sp.setEnabled(self.own_margins.isChecked())
        self.gap.setEnabled(self.columns.value() > 1)

    def _reset(self) -> None:
        self.size_choice.setCurrentIndex(0)
        self.landscape.setChecked(False)
        self.own_margins.setChecked(False)
        self.columns.setValue(1)

    def result_page(self) -> dict:
        page: dict = {}
        size = self.size_choice.currentData()
        if size == "custom":
            page["width_mm"], page["height_mm"] = self.width_mm.value(), self.height_mm.value()
        elif size:
            page["page_size"] = size
        if size and self.landscape.isChecked():
            page["landscape"] = True
        if self.own_margins.isChecked():
            page["margins"] = {k: sp.value() for k, sp in self.margin.items()}
        if self.columns.value() > 1:
            page["columns"] = self.columns.value()
            page["column_gap_mm"] = self.gap.value()
        return page
