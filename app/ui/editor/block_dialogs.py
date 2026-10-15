"""Dialogs for editing non-text blocks: images, tables and recipes."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...domain.book import BookProject
from ...domain.content_blocks import ImageBlock, RecipeBlock, Run, TableBlock, plain_runs, runs_text
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
        for label, sp in zip(("Crop left", "Crop top", "Crop right", "Crop bottom"), self.crop):
            form.addRow(label, sp)
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
                       own_page=self.own_page.isChecked(), crop=crop)


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
