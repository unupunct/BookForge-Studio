"""Dialogs for editing non-text blocks: images, tables and recipes."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QColorDialog, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...domain.book import BookProject
from ...domain.content_blocks import (LAYOUT_KINDS, ImageBlock, LayoutBlock, RecipeBlock, Run, TableBlock,
                                      TextBoxBlock, plain_runs, runs_text)
from ...services.image_service import effective_dpi

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff);;All files (*.*)"


def choose_and_add_image(parent: QWidget, project: BookProject) -> ImageBlock | None:
    path, _ = QFileDialog.getOpenFileName(parent, "Insert image", "", IMAGE_FILTER)
    if not path:
        return None
    try:
        data = Path(path).read_bytes()
        asset = project.add_asset(data, Path(path).name, path)
    except Exception as e:  # unreadable or oversized images are reported, never crash
        QMessageBox.warning(parent, "Image", f"The image could not be added:\n{e}")
        return None
    return ImageBlock(asset=asset.id, alt="")


class ColorButton(QPushButton):
    """A button that shows a colour and opens the colour chooser. An empty colour is allowed when `clearable`."""

    def __init__(self, color: str = "#000000", clearable: bool = False):
        super().__init__()
        self.color = color
        self.clearable = clearable
        self.clicked.connect(self._pick)
        self._paint()

    def _paint(self) -> None:
        if self.color:
            self.setText(self.color.upper())
            c = QColor(self.color)
            fg = "#000" if c.lightness() > 140 else "#FFF"
            self.setStyleSheet(f"background:{self.color}; color:{fg}; padding:3px 10px;")
        else:
            self.setText("none")
            self.setStyleSheet("")

    def _pick(self) -> None:
        c = QColorDialog.getColor(QColor(self.color or "#FFFFFF"), self, "Colour")
        if c.isValid():
            self.color = c.name()
            self._paint()
        elif self.clearable:
            self.color = ""
            self._paint()

    def set_color(self, color: str) -> None:
        self.color = color
        self._paint()


class _Buttons(QDialogButtonBox):
    def __init__(self, dlg: QDialog):
        super().__init__(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.accepted.connect(dlg.accept)
        self.rejected.connect(dlg.reject)


class ImageDialog(QDialog):
    def __init__(self, parent: QWidget, block: ImageBlock, project: BookProject):
        super().__init__(parent)
        self.setWindowTitle("Image properties")
        self.block, self.project = block, project
        asset = project.assets.get(block.asset)
        lay = QVBoxLayout(self)
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumHeight(140)
        if asset and asset.data:
            img = QImage.fromData(asset.data)
            self.preview.setPixmap(QPixmap.fromImage(img).scaled(360, 200, Qt.KeepAspectRatio,
                                                                 Qt.SmoothTransformation))
        else:
            self.preview.setText("Image file is missing")
        lay.addWidget(self.preview)
        form = QFormLayout()
        self.caption = QLineEdit(runs_text(block.caption))
        self.caption.setAccessibleName("Caption")
        self.alt = QLineEdit(block.alt)
        self.alt.setAccessibleName("Alternative text")
        self.width = QDoubleSpinBox(minimum=5, maximum=100, suffix=" %", value=block.width_pct)
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right"])
        self.align.setCurrentText(block.align)
        self.own_page = QCheckBox("Place on its own page")
        self.own_page.setChecked(block.own_page)
        self.place = QComboBox()
        for key, label in (("inline", "In the text (flows with it)"), ("wrap_left", "Float left, text wraps beside it"),
                           ("wrap_right", "Float right, text wraps beside it"),
                           ("page", "Pinned at an exact spot of the page")):
            self.place.addItem(label, key)
        self.place.setCurrentIndex(max(self.place.findData(block.place), 0))
        self.px = QDoubleSpinBox(minimum=-50, maximum=150, decimals=1, suffix=" %", value=block.px * 100)
        self.py = QDoubleSpinBox(minimum=-50, maximum=150, decimals=1, suffix=" %", value=block.py * 100)
        self.pw = QDoubleSpinBox(minimum=2, maximum=150, decimals=1, suffix=" %", value=block.pw * 100)
        self.rotation = QDoubleSpinBox(minimum=-180, maximum=180, decimals=1, suffix=" °", value=block.rotation)
        self.opacity = QDoubleSpinBox(minimum=0, maximum=100, decimals=0, suffix=" %", value=block.opacity * 100)
        self.crop = [QDoubleSpinBox(minimum=0, maximum=90, suffix=" %", decimals=1) for _ in range(4)]
        if block.crop and len(block.crop) == 4:
            l, t, r, b = block.crop
            for sp, v in zip(self.crop, (l * 100, t * 100, (1 - r) * 100, (1 - b) * 100)):
                sp.setValue(v)
        form.addRow("Caption", self.caption)
        form.addRow("Alternative text", self.alt)
        form.addRow("Width (of text area)", self.width)
        form.addRow("Alignment", self.align)
        form.addRow("", self.own_page)
        form.addRow("Placement", self.place)
        pin = [("Left (page width)", self.px), ("Top (page height)", self.py), ("Width (page width)", self.pw),
               ("Rotation", self.rotation), ("Opacity", self.opacity)]
        self._pin_rows = pin
        for label, sp in pin:
            form.addRow(label, sp)
        for label, sp in zip(("Crop left", "Crop top", "Crop right", "Crop bottom"), self.crop):
            form.addRow(label, sp)
        self.place.currentIndexChanged.connect(self._place_changed)
        self._place_changed()
        lay.addLayout(form)
        self.info = QLabel()
        self.info.setProperty("muted", True)
        self.info.setWordWrap(True)
        if asset and asset.data:
            self.info.setText(f"{asset.width} × {asset.height} px  •  aspect ratio is always preserved")
        lay.addWidget(self.info)
        swap = QPushButton("Replace image file…")
        swap.clicked.connect(self._replace)
        lay.addWidget(swap)
        lay.addWidget(_Buttons(self))

    def _place_changed(self) -> None:
        pinned = self.place.currentData() == "page"
        for _label, sp in self._pin_rows:
            sp.setEnabled(pinned)
        self.own_page.setEnabled(self.place.currentData() == "inline")
        self.width.setEnabled(not pinned)

    def _replace(self) -> None:
        nb = choose_and_add_image(self, self.project)
        if nb:
            self.block = replace(self.block, asset=nb.asset)
            asset = self.project.assets[nb.asset]
            self.preview.setPixmap(QPixmap.fromImage(QImage.fromData(asset.data)).scaled(
                360, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def result_block(self) -> ImageBlock:
        c = [sp.value() / 100.0 for sp in self.crop]
        crop = None
        if any(c):
            crop = [c[0], c[1], 1 - c[2], 1 - c[3]]
            if crop[2] - crop[0] < 0.05 or crop[3] - crop[1] < 0.05:
                crop = None
        return replace(self.block, caption=plain_runs(self.caption.text()), alt=self.alt.text(),
                       width_pct=self.width.value(), align=self.align.currentText(),
                       own_page=self.own_page.isChecked() and self.place.currentData() == "inline", crop=crop,
                       place=self.place.currentData(), px=self.px.value() / 100, py=self.py.value() / 100,
                       pw=self.pw.value() / 100, rotation=self.rotation.value(), opacity=self.opacity.value() / 100)


class TextBoxDialog(QDialog):
    """Plain text pinned at an exact spot of the page."""

    def __init__(self, parent: QWidget, block: TextBoxBlock):
        super().__init__(parent)
        self.setWindowTitle("Text box")
        self.block = block
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit(block.text)
        self.text.setMinimumHeight(110)
        self.text.setAccessibleName("Text box content")
        lay.addWidget(self.text)
        form = QFormLayout()

        def pct(v, lo=0.0, hi=100.0):
            return QDoubleSpinBox(minimum=lo, maximum=hi, decimals=1, suffix=" %", value=v * 100)
        self.px, self.py, self.pw, self.ph = pct(block.px, -50, 150), pct(block.py, -50, 150), pct(block.pw, 2, 150), pct(block.ph, 2, 150)
        form.addRow("Left (page width)", self.px)
        form.addRow("Top (page height)", self.py)
        form.addRow("Width (page width)", self.pw)
        form.addRow("Height (page height)", self.ph)
        self.font_family = QLineEdit(block.font_family)
        self.font_family.setPlaceholderText("book's body font")
        self.size_pt = QDoubleSpinBox(minimum=5, maximum=200, decimals=1, suffix=" pt", value=block.size)
        self.bold = QCheckBox("Bold")
        self.bold.setChecked(block.bold)
        self.italic = QCheckBox("Italic")
        self.italic.setChecked(block.italic)
        self.color = ColorButton(block.color)
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right"])
        self.align.setCurrentText(block.align)
        self.valign = QComboBox()
        self.valign.addItems(["top", "middle", "bottom"])
        self.valign.setCurrentText(block.valign)
        self.bg = ColorButton(block.background, clearable=True)
        self.bg.setToolTip("Click to choose; cancel the chooser to remove the background")
        self.bg_opacity = QDoubleSpinBox(minimum=0, maximum=100, decimals=0, suffix=" %", value=block.background_opacity * 100)
        self.rotation = QDoubleSpinBox(minimum=-180, maximum=180, decimals=1, suffix=" °", value=block.rotation)
        self.autofit = QCheckBox("Shrink the text to fit the box")
        self.autofit.setChecked(block.autofit)
        for label, w in (("Font", self.font_family), ("Size", self.size_pt), ("", self.bold), ("", self.italic),
                         ("Text colour", self.color), ("Align", self.align), ("Vertical", self.valign),
                         ("Background", self.bg), ("Background opacity", self.bg_opacity),
                         ("Rotation", self.rotation), ("", self.autofit)):
            form.addRow(label, w)
        lay.addLayout(form)
        hint = QLabel("A text box stays where you put it and does not move the text. It is drawn over what was "
                      "placed before it on the same page. You can also drag it in the preview.")
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        lay.addWidget(hint)
        lay.addWidget(_Buttons(self))

    def result_block(self) -> TextBoxBlock:
        return replace(self.block, text=self.text.toPlainText(), px=self.px.value() / 100, py=self.py.value() / 100,
                       pw=self.pw.value() / 100, ph=self.ph.value() / 100, font_family=self.font_family.text().strip(),
                       size=self.size_pt.value(), bold=self.bold.isChecked(), italic=self.italic.isChecked(),
                       color=self.color.color or "#222222", align=self.align.currentText(),
                       valign=self.valign.currentText(), background=self.bg.color,
                       background_opacity=self.bg_opacity.value() / 100, rotation=self.rotation.value(),
                       autofit=self.autofit.isChecked())


class LayoutDialog(QDialog):
    """A designed page: photo page with overlay, image beside text, image over text, quote page."""

    def __init__(self, parent: QWidget, block: LayoutBlock, project: BookProject):
        super().__init__(parent)
        self.setWindowTitle("Page layout")
        self.block, self.project = block, project
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        for k, label in LAYOUT_KINDS.items():
            self.kind.addItem(label, k)
        self.kind.setCurrentIndex(max(self.kind.findData(block.layout), 0))
        self.image_label = QLabel()
        self.image_btn = QPushButton("Choose image…")
        self.image_btn.clicked.connect(self._choose)
        self.headline = QLineEdit(block.headline)
        self.text = QPlainTextEdit(block.text)
        self.text.setMinimumHeight(110)
        self.share = QDoubleSpinBox(minimum=15, maximum=80, decimals=0, suffix=" %", value=block.image_pct)
        self.overlay = QComboBox()
        for k, label in (("bottom", "Band at the bottom"), ("top", "Band at the top"), ("middle", "Band in the middle"),
                         ("none", "No overlay")):
            self.overlay.addItem(label, k)
        self.overlay.setCurrentIndex(max(self.overlay.findData(block.overlay), 0))
        self.overlay_color = ColorButton(block.overlay_color)
        self.overlay_opacity = QDoubleSpinBox(minimum=0, maximum=100, decimals=0, suffix=" %", value=block.overlay_opacity * 100)
        self.text_color = ColorButton(block.text_color)
        self.font_family = QLineEdit(block.font_family)
        self.font_family.setPlaceholderText("book's body font")
        self.size_pt = QDoubleSpinBox(minimum=6, maximum=60, decimals=1, suffix=" pt", value=block.size)
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right"])
        self.align.setCurrentText(block.align)
        self.rows = {
            "layout": ("Layout", self.kind), "image": ("Image", self.image_btn), "imglabel": ("", self.image_label),
            "headline": ("Headline / caption", self.headline), "text": ("Text", self.text),
            "share": ("Image share of the page", self.share), "overlay": ("Overlay", self.overlay),
            "ocolor": ("Overlay colour", self.overlay_color), "oopacity": ("Overlay opacity", self.overlay_opacity),
            "tcolor": ("Overlay text colour", self.text_color), "font": ("Font", self.font_family),
            "size": ("Text size", self.size_pt), "align": ("Align", self.align)}
        self._labels = {}
        for key, (label, w) in self.rows.items():
            lbl = QLabel(label)
            self._labels[key] = lbl
            form.addRow(lbl, w)
        lay.addLayout(form)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setProperty("muted", True)
        lay.addWidget(self.hint)
        lay.addWidget(_Buttons(self))
        self.kind.currentIndexChanged.connect(self._sync)
        self._show_image()
        self._sync()

    def _show_image(self) -> None:
        a = self.project.assets.get(self.block.asset)
        self.image_label.setText(a.filename if a else "no image chosen")

    def _choose(self) -> None:
        nb = choose_and_add_image(self, self.project)
        if nb:
            self.block = replace(self.block, asset=nb.asset)
            self._show_image()

    def _sync(self) -> None:
        kind = self.kind.currentData()
        photo = kind == "photo_full"
        quote = kind == "quote_page"
        visible = {"layout": True, "image": not quote, "imglabel": not quote, "headline": True,
                   "text": True, "share": kind in ("image_left", "image_right", "image_top"),
                   "overlay": photo, "ocolor": photo, "oopacity": photo, "tcolor": photo, "font": True,
                   "size": True, "align": True}
        for key, (label, w) in self.rows.items():
            w.setVisible(visible[key])
            self._labels[key].setVisible(visible[key])
        self._labels["headline"].setText({"photo_full": "Headline on the photo", "quote_page": "Attribution"}.get(
            kind, "Caption under the image"))
        self._labels["share"].setText("Image height" if kind == "image_top" else "Image width")
        self.hint.setText({"photo_full": "The photo covers the whole page, without margins or a page number.",
                           "quote_page": "A quotation centred on its own page. The text shrinks to fit.",
                           }.get(kind, "A page of its own inside the margins. The text shrinks to fit its area; "
                                       "blank lines make paragraph gaps."))

    def result_block(self) -> LayoutBlock:
        return replace(self.block, layout=self.kind.currentData(), headline=self.headline.text().strip(),
                       text=self.text.toPlainText().strip("\n"), image_pct=self.share.value(),
                       overlay=self.overlay.currentData(), overlay_color=self.overlay_color.color,
                       overlay_opacity=self.overlay_opacity.value() / 100, text_color=self.text_color.color,
                       font_family=self.font_family.text().strip(), size=self.size_pt.value(), align=self.align.currentText())


class TableDialog(QDialog):
    def __init__(self, parent: QWidget, block: TableBlock):
        super().__init__(parent)
        self.setWindowTitle("Table")
        self.block = block
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        for text, fn in (("Add row", self._add_row), ("Add column", self._add_col),
                         ("Delete row", self._del_row), ("Delete column", self._del_col)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        lay.addLayout(bar)
        rows = block.rows or [[""]]
        ncols = max(len(r) for r in rows)
        self.table = QTableWidget(len(rows), ncols)
        self.table.setAccessibleName("Table cells")
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        for r, row in enumerate(rows):
            for c in range(ncols):
                self.table.setItem(r, c, QTableWidgetItem(row[c] if c < len(row) else ""))
        lay.addWidget(self.table, 1)
        form = QFormLayout()
        self.header_rows = QSpinBox(minimum=0, maximum=5, value=block.header_rows)
        self.caption = QLineEdit(runs_text(block.caption))
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right"])
        if block.align:
            self.align.setCurrentText(block.align[0])
        form.addRow("Header rows (repeated on each page)", self.header_rows)
        form.addRow("Caption", self.caption)
        form.addRow("Column alignment", self.align)
        lay.addLayout(form)
        lay.addWidget(_Buttons(self))

    def _add_row(self) -> None:
        self.table.insertRow(self.table.rowCount())
        for c in range(self.table.columnCount()):
            self.table.setItem(self.table.rowCount() - 1, c, QTableWidgetItem(""))

    def _add_col(self) -> None:
        self.table.insertColumn(self.table.columnCount())
        for r in range(self.table.rowCount()):
            self.table.setItem(r, self.table.columnCount() - 1, QTableWidgetItem(""))

    def _del_row(self) -> None:
        if self.table.rowCount() > 1:
            self.table.removeRow(self.table.currentRow() if self.table.currentRow() >= 0
                                 else self.table.rowCount() - 1)

    def _del_col(self) -> None:
        if self.table.columnCount() > 1:
            self.table.removeColumn(self.table.currentColumn() if self.table.currentColumn() >= 0
                                    else self.table.columnCount() - 1)

    def result_block(self) -> TableBlock:
        rows = [[(self.table.item(r, c).text() if self.table.item(r, c) else "")
                 for c in range(self.table.columnCount())] for r in range(self.table.rowCount())]
        n = self.table.columnCount()
        return replace(self.block, rows=rows, header_rows=self.header_rows.value(),
                       caption=plain_runs(self.caption.text()),
                       align=[self.align.currentText()] * n)


class RecipeDialog(QDialog):
    def __init__(self, parent: QWidget, block: RecipeBlock, project: BookProject):
        super().__init__(parent)
        self.setWindowTitle("Recipe")
        self.block, self.project = block, project
        self.resize(560, 640)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(block.title)
        self.desc = QPlainTextEdit(block.description)
        self.desc.setFixedHeight(60)
        self.prep = QLineEdit(block.prep_time)
        self.cook = QLineEdit(block.cook_time)
        self.serv = QLineEdit(block.servings)
        self.ingr = QPlainTextEdit("\n".join(block.ingredients))
        self.ingr.setPlaceholderText("One ingredient per line")
        self.steps = QPlainTextEdit("\n".join(block.instructions))
        self.steps.setPlaceholderText("One step per line")
        self.notes = QPlainTextEdit(block.notes)
        self.notes.setFixedHeight(50)
        self.nutr = QLineEdit(block.nutrition)
        self.nutr.setPlaceholderText("Only if you have supplied values yourself")
        form.addRow("Title", self.title)
        form.addRow("Description", self.desc)
        form.addRow("Preparation time", self.prep)
        form.addRow("Cooking time", self.cook)
        form.addRow("Servings", self.serv)
        form.addRow("Ingredients", self.ingr)
        form.addRow("Instructions", self.steps)
        form.addRow("Notes", self.notes)
        form.addRow("Nutrition (optional)", self.nutr)
        self.image_label = QLabel(project.assets[block.image].filename if block.image in project.assets else "No image")
        pick = QPushButton("Choose image…")
        pick.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.image_label, 1)
        row.addWidget(pick)
        form.addRow("Image", row)
        lay.addLayout(form)
        lay.addWidget(_Buttons(self))

    def _pick(self) -> None:
        nb = choose_and_add_image(self, self.project)
        if nb:
            self.block = replace(self.block, image=nb.asset)
            self.image_label.setText(self.project.assets[nb.asset].filename)

    def result_block(self) -> RecipeBlock:
        lines = lambda w: [l.strip() for l in w.toPlainText().splitlines() if l.strip()]
        return replace(self.block, title=self.title.text().strip(), description=self.desc.toPlainText().strip(),
                       prep_time=self.prep.text().strip(), cook_time=self.cook.text().strip(),
                       servings=self.serv.text().strip(), ingredients=lines(self.ingr),
                       instructions=lines(self.steps), notes=self.notes.toPlainText().strip(),
                       nutrition=self.nutr.text().strip())
