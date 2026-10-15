"""Settings, validation report and cover design dialogs."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from ...application_state import AppState
from ...domain.layouts import CoverDesign
from ...layout.model import Page
from ...layout.page_builder import cover_items
from ...layout.typography import LOGICAL_FAMILIES, fonts
from ...services.validation_service import ValidationReport
from .. import theme
from ..editor.block_dialogs import choose_and_add_image
from ..preview.page_renderer import render_page


class SettingsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Settings")
        form = QFormLayout(self)
        d = state.settings_store.data
        self.autosave = QSpinBox(minimum=0, maximum=3600, suffix=" s", value=d.autosave_seconds)
        self.autosave.setToolTip("0 turns autosave off")
        self.scale = QDoubleSpinBox(minimum=0.8, maximum=2.0, singleStep=0.1, value=d.ui_scale)
        self.scale.setToolTip("Interface text scale. Takes effect after restarting.")
        form.addRow("Autosave interval", self.autosave)
        form.addRow("Interface scale (restart)", self.scale)
        info = QLabel("Fonts used for layout:\n" + ", ".join(fonts.installed_families()))
        info.setWordWrap(True)
        theme.set_muted(info)
        form.addRow(info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _ok(self) -> None:
        d = self.state.settings_store.data
        d.autosave_seconds = self.autosave.value()
        d.ui_scale = self.scale.value()
        self.state.settings_store.save()
        self.state.apply_autosave_interval()
        self.accept()


class ValidationDialog(QDialog):
    navigate = Signal(object)  # ValidationIssue

    def __init__(self, report: ValidationReport, parent=None):
        super().__init__(parent)
        self.report = report
        self.setWindowTitle("Book validation")
        self.resize(640, 460)
        self.setModal(False)
        lay = QVBoxLayout(self)
        head = QLabel(("✔ No problems found." if not report.issues else report.summary()))
        theme.set_heading(head)
        lay.addWidget(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Severity", "Issue"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 90)
        self.tree.setAccessibleName("Validation issues")
        col = {"error": theme.ERROR, "warning": theme.WARNING, "info": theme.TEXT_MUTED}
        order = {"error": 0, "warning": 1, "info": 2}
        for n, i in enumerate(sorted(report.issues, key=lambda x: order.get(x.severity, 3))):
            it = QTreeWidgetItem([i.severity.upper(), i.message +
                                  (f"  (page {i.page_index + 1})" if i.page_index is not None else "")])
            it.setForeground(0, QBrush(QColor(col.get(i.severity, theme.TEXT))))
            it.setData(0, Qt.UserRole, i)
            self.tree.addTopLevelItem(it)
        self.tree.itemDoubleClicked.connect(lambda it, _: self.navigate.emit(it.data(0, Qt.UserRole)))
        lay.addWidget(self.tree, 1)
        hint = QLabel("Double-click an issue to jump to it.")
        theme.set_muted(hint)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.close)
        lay.addWidget(bb)


class CoverDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.design = CoverDesign.from_dict(state.project.settings.cover.to_dict())
        self.setWindowTitle("Cover design")
        self.resize(820, 560)
        root = QHBoxLayout(self)
        form = QFormLayout()
        self.enabled = QCheckBox("Book has covers")
        self.enabled.setChecked(self.design.enabled)
        self.bg = self._color_btn("background")
        self.bg2 = self._color_btn("background2")
        self.use_grad = QCheckBox("Vertical gradient to second color")
        self.use_grad.setChecked(bool(self.design.background2))
        self.title_c = self._color_btn("title_color")
        self.author_c = self._color_btn("author_color")
        self.family = QComboBox()
        self.family.setEditable(True)
        self.family.addItems(list(LOGICAL_FAMILIES) + fonts.installed_families())
        self.family.setCurrentText(self.design.font_family)
        self.t_size = QDoubleSpinBox(minimum=10, maximum=120, value=self.design.title_size)
        self.s_size = QDoubleSpinBox(minimum=8, maximum=80, value=self.design.subtitle_size)
        self.a_size = QDoubleSpinBox(minimum=8, maximum=80, value=self.design.author_size)
        self.img_label = QLabel(self.state.project.assets[self.design.image_asset].filename
                                if self.design.image_asset in self.state.project.assets else "No image")
        img_btn = QPushButton("Choose image…")
        clear = QPushButton("Remove")
        row = QHBoxLayout()
        row.addWidget(self.img_label, 1)
        row.addWidget(img_btn)
        row.addWidget(clear)
        self.mode = QComboBox()
        self.mode.addItem("Fill the cover (centre-cropped)", "behind")
        self.mode.addItem("Fit in the upper part", "top")
        self.mode.setCurrentIndex(0 if self.design.image_mode == "behind" else 1)
        self.back = QPlainTextEdit(self.design.back_text)
        self.back.setFixedHeight(70)
        self.pub = QLineEdit(self.design.publisher_text)
        self.dpi_note = QLabel("")
        self.dpi_note.setWordWrap(True)
        form.addRow(self.enabled)
        form.addRow("Background", self.bg)
        form.addRow(self.use_grad)
        form.addRow("Gradient end", self.bg2)
        form.addRow("Title color", self.title_c)
        form.addRow("Author color", self.author_c)
        form.addRow("Font", self.family)
        form.addRow("Title size", self.t_size)
        form.addRow("Subtitle size", self.s_size)
        form.addRow("Author size", self.a_size)
        form.addRow("Image", row)
        form.addRow("Image mode", self.mode)
        form.addRow("", self.dpi_note)
        form.addRow("Back cover text", self.back)
        form.addRow("Publisher text", self.pub)
        spine = QLabel("")
        spine.setWordWrap(True)
        theme.set_muted(spine)
        self.spine = spine
        self.thick = QDoubleSpinBox(minimum=0.01, maximum=1.0, singleStep=0.005, decimals=3, suffix=" mm",
                                    value=state.project.settings.paper_thickness_mm)
        self.thick.setToolTip("Thickness of ONE leaf (two pages) of your paper, as given by your printer")
        form.addRow("Paper thickness per leaf", self.thick)
        form.addRow("", self.spine)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        png = bb.addButton("Export front cover PNG…", QDialogButtonBox.ActionRole)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(320, 460)
        root.addLayout(form, 1)
        root.addWidget(self.preview, 1)
        for w in (self.enabled, self.use_grad):
            w.toggled.connect(self._update)
        for w in (self.t_size, self.s_size, self.a_size, self.thick):
            w.valueChanged.connect(self._update)
        self.family.currentTextChanged.connect(self._update)
        self.mode.currentIndexChanged.connect(self._update)
        self.back.textChanged.connect(self._update)
        self.pub.textChanged.connect(self._update)
        img_btn.clicked.connect(self._pick_image)
        clear.clicked.connect(self._clear_image)
        png.clicked.connect(self._export_png)
        self._update()

    def _color_btn(self, attr: str) -> QPushButton:
        b = QPushButton(getattr(self.design, attr) or "#000000")
        b.clicked.connect(lambda: self._pick_color(attr, b))
        self._style_btn(b, getattr(self.design, attr) or "#000000")
        return b

    @staticmethod
    def _style_btn(b: QPushButton, color: str) -> None:
        b.setText(color)
        b.setStyleSheet(f"background: {color}; color: {'#000' if QColor(color).lightness() > 128 else '#fff'};")

    def _pick_color(self, attr: str, btn: QPushButton) -> None:
        c = QColorDialog.getColor(QColor(getattr(self.design, attr) or "#000000"), self, "Color")
        if c.isValid():
            setattr(self.design, attr, c.name())
            self._style_btn(btn, c.name())
            if attr == "background2":
                self.use_grad.setChecked(True)
            self._update()

    def _pick_image(self) -> None:
        blk = choose_and_add_image(self, self.state.project)
        if blk:
            self.design.image_asset = blk.asset
            self.img_label.setText(self.state.project.assets[blk.asset].filename)
            self._update()

    def _clear_image(self) -> None:
        self.design.image_asset = ""
        self.img_label.setText("No image")
        self._update()

    def _collect(self) -> CoverDesign:
        d = self.design
        d.enabled = self.enabled.isChecked()
        d.background2 = d.background2 if self.use_grad.isChecked() and d.background2 else (
            "#000000" if self.use_grad.isChecked() else None)
        d.font_family = self.family.currentText() or "serif"
        d.title_size, d.subtitle_size, d.author_size = self.t_size.value(), self.s_size.value(), self.a_size.value()
        d.image_mode = self.mode.currentData()
        d.back_text, d.publisher_text = self.back.toPlainText(), self.pub.text()
        return d

    def _front_image(self, scale: float):
        from ...domain.book import BookProject
        tmp = self.state.project.snapshot()
        tmp.settings.cover = self._collect()
        w, h = tmp.settings.page_size_pt()
        items = cover_items(tmp, w, h, False)
        page = Page(0, w, h, "recto", (0, 0, w, h), items=items, full_bleed=True)
        return render_page(page, tmp.assets, scale)

    def _update(self) -> None:
        self._collect()
        self.preview.setPixmap(QPixmap.fromImage(self._front_image(440.0 / self.state.project.settings.page_size_pt()[1])))
        a = self.state.project.assets.get(self.design.image_asset)
        w_in = self.state.project.settings.width_mm / 25.4
        if a and a.data:
            dpi = a.width / (w_in + 2 * self.state.project.settings.bleed_mm / 25.4)
            ok = dpi >= 300
            self.dpi_note.setText(f"Cover image resolution at print size: {dpi:.0f} dpi "
                                  + ("— good for print." if ok else "— below 300 dpi; it may print soft."))
            self.dpi_note.setStyleSheet(f"color: {theme.OK if ok else theme.WARNING};")
        else:
            self.dpi_note.setText("")
        pages = self.state.layout.page_count if self.state.layout else 0
        if pages:
            spine = pages / 2 * self.thick.value()
            self.spine.setText(f"Estimated spine for {pages} pages: {spine:.1f} mm "
                               "(pages ÷ 2 × leaf thickness). Printers differ — confirm the value "
                               "and cover template with your printer.")

    def _export_png(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Export front cover", "front-cover.png", "PNG (*.png)")
        if not p:
            return
        w_pt = self.state.project.settings.page_size_pt()[0]
        scale = 300.0 / 72.0
        self._front_image(scale).save(p)

    def _ok(self) -> None:
        d = self._collect()
        thick = self.thick.value()

        def fn(p) -> None:
            p.settings.cover = d
            p.settings.paper_thickness_mm = thick
        self.state.edit("Change cover", fn, kind="settings")
        self.accept()
