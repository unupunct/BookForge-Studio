"""Layered cover designer: presets, palettes, shapes, patterns, image filters, text and exports."""
from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget)

from ...application_state import AppState
from ...domain.layouts import MM_TO_PT, CoverDesign, CoverLayer
from ...layout.cover_builder import PATTERNS
from ...layout.model import Page
from ...layout.page_builder import cover_items
from ...layout.typography import LOGICAL_FAMILIES, fonts
from ...services.cover_presets import PALETTES, PRESETS, apply_palette, apply_preset
from ...services.cover_service import CoverExportError, export_cover_pdf, spine_width_mm
from ...services.image_service import effective_dpi
from .. import theme
from ..editor.block_dialogs import choose_and_add_image
from ..preview.page_renderer import render_page

KIND_LABEL = {"text": "Text", "image": "Image", "rect": "Rectangle", "ellipse": "Ellipse", "line": "Line",
              "frame": "Frame", "pattern": "Pattern"}


class CoverCanvas(QWidget):
    layer_selected = Signal(str)
    layer_edited = Signal()

    def __init__(self, dlg: "CoverDialog"):
        super().__init__()
        self.dlg = dlg
        self.setMinimumSize(340, 460)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Cover canvas")
        self._img = None
        self._scale = 1.0
        self._origin = QPointF(0, 0)
        self._drag = None

    def refresh(self) -> None:
        self._img = None
        self.update()

    def _geometry(self) -> tuple[float, float, float]:
        W, H = self.dlg.book.settings.page_size_pt()
        s = min((self.width() - 24) / W, (self.height() - 24) / H)
        return s, (self.width() - W * s) / 2, (self.height() - H * s) / 2

    def _page_image(self, s: float):
        key = round(s, 3)
        if self._img is None or self._img[0] != key:
            W, H = self.dlg.book.settings.page_size_pt()
            items = cover_items(self.dlg.book, W, H, self.dlg.side == "back")
            page = Page(0, W, H, "recto", (0, 0, W, H), items=items, full_bleed=True)
            self._img = (key, render_page(page, self.dlg.book.assets, s))
        return self._img[1]

    def _rect_of(self, L: CoverLayer, s: float, ox: float, oy: float) -> QRectF:
        W, H = self.dlg.book.settings.page_size_pt()
        return QRectF(ox + L.x * W * s, oy + L.y * H * s, L.w * W * s, max(L.h * H * s, 6))

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        s, ox, oy = self._geometry()
        W, H = self.dlg.book.settings.page_size_pt()
        p.fillRect(QRectF(ox + 4, oy + 5, W * s, H * s), QColor(0, 0, 0, 90))
        p.drawImage(QPointF(ox, oy), self._page_image(s))
        L = self.dlg.current_layer()
        if L is not None and L.visible:
            r = self._rect_of(L, s, ox, oy)
            p.save()
            c = r.center()
            p.translate(c)
            p.rotate(-L.rotation)
            p.translate(-c)
            pen = QPen(QColor(theme.ACCENT), 1.5, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            p.setBrush(QColor(theme.ACCENT))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(r.right() - 6, r.bottom() - 6, 12, 12))
            p.restore()
        p.end()

    def _layer_at(self, pos: QPointF):
        s, ox, oy = self._geometry()
        for L in reversed(self.dlg.layers()):
            if L.visible and not L.locked and self._rect_of(L, s, ox, oy).adjusted(-4, -4, 4, 4).contains(pos):
                return L
        return None

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        s, ox, oy = self._geometry()
        cur = self.dlg.current_layer()
        if cur is not None and cur.visible and not cur.locked:
            r = self._rect_of(cur, s, ox, oy)
            if QRectF(r.right() - 10, r.bottom() - 10, 20, 20).contains(pos):
                self._drag = ("resize", cur, pos, (cur.w, cur.h))
                return
        hit = self._layer_at(pos)
        if hit is not None:
            self.layer_selected.emit(hit.id)
            self._drag = ("move", hit, pos, (hit.x, hit.y))

    def mouseMoveEvent(self, e) -> None:
        if not self._drag:
            return
        mode, L, start, orig = self._drag
        s, ox, oy = self._geometry()
        W, H = self.dlg.book.settings.page_size_pt()
        dx, dy = (e.position().x() - start.x()) / (W * s), (e.position().y() - start.y()) / (H * s)
        if mode == "move":
            L.x, L.y = round(orig[0] + dx, 4), round(orig[1] + dy, 4)
        else:
            L.w, L.h = max(round(orig[0] + dx, 4), 0.01), max(round(orig[1] + dy, 4), 0.0)
        self.refresh()
        self.layer_edited.emit()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            self._drag = None
            self.layer_edited.emit()

    def keyPressEvent(self, e) -> None:
        L = self.dlg.current_layer()
        step = 0.01 if e.modifiers() & Qt.ShiftModifier else 0.002
        d = {Qt.Key_Left: (-step, 0), Qt.Key_Right: (step, 0), Qt.Key_Up: (0, -step), Qt.Key_Down: (0, step)}.get(e.key())
        if L is not None and d and not L.locked:
            L.x, L.y = round(L.x + d[0], 4), round(L.y + d[1], 4)
            self.refresh()
            self.layer_edited.emit()
        elif e.key() == Qt.Key_Delete:
            self.dlg.delete_layer()
        else:
            super().keyPressEvent(e)


class CoverDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Cover designer")
        self.resize(1240, 760)
        self.design = CoverDesign.from_dict(state.project.settings.cover.to_dict())
        self.book = state.project.snapshot()
        self.book.settings.cover = self.design
        self.side = "front"
        self._loading = False
        self._ensure_layers()

        root = QHBoxLayout(self)
        # ---- left: design controls and layers
        left = QVBoxLayout()
        top = QHBoxLayout()
        self.side_btn = QPushButton("Front cover")
        self.side_btn.setCheckable(True)
        self.side_btn.setToolTip("Switch between front and back cover")
        self.side_btn.clicked.connect(self._toggle_side)
        self.preset = QComboBox()
        self.preset.addItem("Presets…", "")
        for k, (label, _) in PRESETS.items():
            self.preset.addItem(label, k)
        self.preset.activated.connect(self._preset_chosen)
        self.palette = QComboBox()
        self.palette.addItem("Colour palettes…", "")
        for k, v in PALETTES.items():
            self.palette.addItem(v[0], k)
        self.palette.activated.connect(self._palette_chosen)
        top.addWidget(self.side_btn)
        top.addWidget(self.preset, 1)
        top.addWidget(self.palette, 1)
        left.addLayout(top)

        bg = QGroupBox("Background")
        bf = QFormLayout(bg)
        self.bg_btn = QPushButton()
        self.bg_btn.clicked.connect(lambda: self._pick_bg(False))
        self.grad = QCheckBox("Vertical gradient")
        self.bg2_btn = QPushButton()
        self.bg2_btn.clicked.connect(lambda: self._pick_bg(True))
        self.grad.toggled.connect(self._grad_toggled)
        bf.addRow("Colour", self.bg_btn)
        bf.addRow(self.grad, self.bg2_btn)
        left.addWidget(bg)

        self.layer_list = QListWidget()
        self.layer_list.setAccessibleName("Cover layers")
        self.layer_list.setToolTip("Layers, top of the list = in front. Tick to show or hide.")
        self.layer_list.currentRowChanged.connect(self._row_changed)
        self.layer_list.itemChanged.connect(self._item_toggled)
        left.addWidget(self.layer_list, 1)
        add_row = QHBoxLayout()
        add = QPushButton("+ Add")
        menu = QMenu(self)
        for kind in ("text", "image", "rect", "ellipse", "line", "frame", "pattern"):
            menu.addAction(KIND_LABEL[kind], lambda k=kind: self.add_layer(k))
        add.setMenu(menu)
        for text, tip, fn in (("▲", "Bring forward", lambda: self.move_layer(1)),
                              ("▼", "Send backward", lambda: self.move_layer(-1)),
                              ("Duplicate", "Duplicate the layer", self.duplicate_layer),
                              ("Delete", "Delete the layer (Delete key)", self.delete_layer)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            add_row.addWidget(b)
        add_row.insertWidget(0, add)
        left.addLayout(add_row)
        auto = QPushButton("Reset to automatic layout")
        auto.setToolTip("Remove all layers and let the title, author and image fields generate the cover")
        auto.clicked.connect(self._auto)
        left.addWidget(auto)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        root.addWidget(lw)

        # ---- centre: canvas
        self.canvas = CoverCanvas(self)
        self.canvas.layer_selected.connect(self._select_by_id)
        self.canvas.layer_edited.connect(self._canvas_edited)
        root.addWidget(self.canvas, 1)

        # ---- right: properties + exports
        right = QVBoxLayout()
        self.props = QWidget()
        self.form = QFormLayout(self.props)
        self._build_props()
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.props)
        sc.setFrameShape(QScrollArea.NoFrame)
        right.addWidget(sc, 1)
        right.addWidget(self._build_export_box())
        btns = QHBoxLayout()
        ok = QPushButton("Apply to book")
        theme.accent_button(ok)
        cancel = QPushButton("Cancel")
        ok.clicked.connect(self._ok)
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        right.addLayout(btns)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(360)
        root.addWidget(rw)
        self._reload_layers()
        self._sync_bg()

    # --------------------------------------------------------------- layers
    def layers(self) -> list[CoverLayer]:
        return self.design.back_layers if self.side == "back" else self.design.front_layers

    def current_layer(self) -> CoverLayer | None:
        row = self.layer_list.currentRow()
        ls = self.layers()
        idx = len(ls) - 1 - row  # the list shows the top layer first
        return ls[idx] if 0 <= row < len(ls) and 0 <= idx < len(ls) else None

    def _ensure_layers(self) -> None:
        """Materialise the automatic cover as editable layers the first time the editor opens."""
        d = self.design
        if not d.front_layers:
            d.front_layers = self._auto_layers(False)
        if not d.back_layers:
            d.back_layers = self._auto_layers(True)

    def _auto_layers(self, back: bool) -> list[CoverLayer]:
        d = self.design
        if back:
            return [CoverLayer("text", text="{back_text}", role="subtitle", x=0.14, y=0.18, w=0.72, h=0.55, size=11.5,
                               color=d.title_color, line_height=1.4, font_family=d.font_family, name="Back text"),
                    CoverLayer("text", text="{publisher}", role="author", x=0.1, y=0.88, w=0.8, h=0.05, size=10,
                               color=d.author_color, font_family=d.font_family, name="Publisher")]
        out = []
        if d.image_asset:
            out.append(CoverLayer("image", role="photo", asset=d.image_asset, x=0, y=0, w=1, h=1, name="Photo",
                                  fit="cover" if d.image_mode == "behind" else "contain"))
        out += [CoverLayer("text", text="{title}", role="title", x=0.1, y=0.22, w=0.8, h=0.28, size=d.title_size,
                           bold=True, color=d.title_color, font_family=d.font_family, autofit=True,
                           valign="middle", name="Title"),
                CoverLayer("text", text="{subtitle}", role="subtitle", x=0.12, y=0.52, w=0.76, h=0.1,
                           size=d.subtitle_size, italic=True, color=d.title_color, font_family=d.font_family,
                           autofit=True, name="Subtitle"),
                CoverLayer("text", text="{author}", role="author", x=0.1, y=0.84, w=0.8, h=0.07,
                           size=d.author_size, color=d.author_color, font_family=d.font_family,
                           autofit=True, valign="middle", name="Author")]
        return out

    def _auto(self) -> None:
        if QMessageBox.question(self, "Reset cover", "Discard all layers on both sides and rebuild the "
                                "automatic layout?") == QMessageBox.Yes:
            self.design.front_layers = self._auto_layers(False)
            self.design.back_layers = self._auto_layers(True)
            self.design.preset = ""
            self._reload_layers()

    def _reload_layers(self, select_id: str | None = None) -> None:
        self._loading = True
        self.layer_list.clear()
        for L in reversed(self.layers()):
            it = QListWidgetItem(f"{KIND_LABEL.get(L.kind, L.kind)} – {L.name or L.text[:18] or L.kind}"
                                 + ("  \U0001F512" if L.locked else ""))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if L.visible else Qt.Unchecked)
            it.setData(Qt.UserRole, L.id)
            self.layer_list.addItem(it)
        self._loading = False
        if select_id:
            self._select_by_id(select_id)
        elif self.layer_list.count():
            self.layer_list.setCurrentRow(0)
        self._load_props()
        self.canvas.refresh()

    def _select_by_id(self, lid: str) -> None:
        for i in range(self.layer_list.count()):
            if self.layer_list.item(i).data(Qt.UserRole) == lid:
                self.layer_list.setCurrentRow(i)
                return

    def _row_changed(self, _row: int) -> None:
        if not self._loading:
            self._load_props()
            self.canvas.update()

    def _item_toggled(self, it) -> None:
        if self._loading:
            return
        for L in self.layers():
            if L.id == it.data(Qt.UserRole):
                L.visible = it.checkState() == Qt.Checked
        self.canvas.refresh()

    def add_layer(self, kind: str) -> None:
        W, H = self.book.settings.page_size_pt()
        d = {"text": dict(text="Your text", x=0.1, y=0.4, w=0.8, h=0.15, size=22, color=self.design.title_color,
                          font_family=self.design.font_family, name="Text"),
             "image": dict(x=0.1, y=0.1, w=0.8, h=0.5, fit="cover", name="Image"),
             "rect": dict(x=0.15, y=0.65, w=0.7, h=0.1, fill=self.design.author_color, name="Rectangle"),
             "ellipse": dict(x=0.3, y=0.3, w=0.4, h=0.28, fill=self.design.author_color, opacity=0.8, name="Ellipse"),
             "line": dict(x=0.2, y=0.6, w=0.6, h=0.0, stroke=self.design.author_color, stroke_width=1.5, name="Line"),
             "frame": dict(x=0.06, y=0.05, w=0.88, h=0.9, stroke=self.design.author_color, stroke_width=1.5, name="Frame"),
             "pattern": dict(x=0.0, y=0.7, w=1.0, h=0.3, pattern="waves", scale=16, fill=self.design.author_color,
                             stroke_width=1.0, opacity=0.4, name="Pattern")}[kind]
        if kind == "image":
            blk = choose_and_add_image(self, self.state.project)
            if not blk:
                return
            self.book.assets[blk.asset] = self.state.project.assets[blk.asset]
            d["asset"] = blk.asset
        L = CoverLayer(kind, **d)
        self.layers().append(L)
        self._reload_layers(L.id)

    def delete_layer(self) -> None:
        L = self.current_layer()
        if L:
            self.layers().remove(L)
            self._reload_layers()

    def duplicate_layer(self) -> None:
        L = self.current_layer()
        if L:
            c = CoverLayer.from_dict(copy.deepcopy(L.to_dict()))
            from ...domain.content_blocks import new_id
            c.id, c.x, c.y, c.name = new_id(), L.x + 0.03, L.y + 0.03, (L.name + " copy").strip()
            self.layers().append(c)
            self._reload_layers(c.id)

    def move_layer(self, delta: int) -> None:
        L = self.current_layer()
        ls = self.layers()
        if L:
            i = ls.index(L)
            j = i + delta
            if 0 <= j < len(ls):
                ls[i], ls[j] = ls[j], ls[i]
                self._reload_layers(L.id)

    # ------------------------------------------------------------ side / bg
    def _toggle_side(self) -> None:
        self.side = "back" if self.side_btn.isChecked() else "front"
        self.side_btn.setText("Back cover" if self.side == "back" else "Front cover")
        self._reload_layers()
        self._sync_bg()

    def _color_btn(self, btn: QPushButton, color: str | None) -> None:
        color = color or "#000000"
        btn.setText(color)
        btn.setStyleSheet(f"background: {color}; color: {'#000' if QColor(color).lightness() > 128 else '#fff'};")

    def _sync_bg(self) -> None:
        self._loading = True
        d = self.design
        if self.side == "back" and d.back_background:
            self._color_btn(self.bg_btn, d.back_background)
            self.grad.setChecked(False)
            self.grad.setEnabled(False)
            self.bg2_btn.setEnabled(False)
        else:
            self._color_btn(self.bg_btn, d.background)
            self.grad.setEnabled(self.side == "front")
            self.grad.setChecked(bool(d.background2) and self.side == "front")
            self.bg2_btn.setEnabled(self.grad.isChecked())
        self._color_btn(self.bg2_btn, d.background2 or "#000000")
        self._loading = False

    def _pick_bg(self, second: bool) -> None:
        d = self.design
        cur = (d.background2 if second else (d.back_background if self.side == "back" and d.back_background
                                              else d.background)) or "#000000"
        c = QColorDialog.getColor(QColor(cur), self, "Background colour")
        if not c.isValid():
            return
        if second:
            d.background2 = c.name()
            self.grad.setChecked(True)
        elif self.side == "back":
            d.back_background = c.name()
        else:
            d.background = c.name()
        self._sync_bg()
        self.canvas.refresh()

    def _grad_toggled(self, on: bool) -> None:
        if self._loading:
            return
        self.design.background2 = (self.design.background2 or "#000000") if on else None
        self.bg2_btn.setEnabled(on)
        self._sync_bg()
        self.canvas.refresh()

    def _preset_chosen(self, _i: int) -> None:
        key = self.preset.currentData()
        if key and QMessageBox.question(self, "Apply preset", "Replace the current cover layers with this "
                                        "preset? Your images are kept.") == QMessageBox.Yes:
            apply_preset(self.book, key)
            self.design = self.book.settings.cover
            self._reload_layers()
            self._sync_bg()
        self.preset.setCurrentIndex(0)

    def _palette_chosen(self, _i: int) -> None:
        key = self.palette.currentData()
        if key:
            apply_palette(self.book, key)
            self._reload_layers(self.current_layer().id if self.current_layer() else None)
            self._sync_bg()
        self.palette.setCurrentIndex(0)

    # ------------------------------------------------------------ properties
    def _build_props(self) -> None:
        f = self.form
        self.name = QLineEdit()
        self.x = self._spin(0, 100, "%")
        self.y = self._spin(0, 100, "%")
        self.w = self._spin(0, 100, "%")
        self.h = self._spin(0, 100, "%")
        self.rot = self._spin(-180, 180, "°")
        self.opacity = self._spin(0, 100, "%")
        self.locked = QCheckBox("Locked (cannot be dragged)")
        for label, w in (("Name", self.name), ("Left", self.x), ("Top", self.y), ("Width", self.w),
                         ("Height", self.h), ("Rotation", self.rot), ("Opacity", self.opacity)):
            f.addRow(label, w)
        f.addRow("", self.locked)
        self.name.editingFinished.connect(lambda: self._set(name=self.name.text()))
        self.locked.toggled.connect(lambda v: self._set(locked=v))
        for sp, attr, k in ((self.x, "x", 0.01), (self.y, "y", 0.01), (self.w, "w", 0.01), (self.h, "h", 0.01)):
            sp.valueChanged.connect(lambda v, a=attr: self._set(**{a: v / 100.0}))
        self.rot.valueChanged.connect(lambda v: self._set(rotation=v))
        self.opacity.valueChanged.connect(lambda v: self._set(opacity=v / 100.0))
        # text
        self.t_group = QGroupBox("Text")
        tf = QFormLayout(self.t_group)
        self.text = QPlainTextEdit()
        self.text.setFixedHeight(70)
        self.text.setToolTip("Tokens: {title} {subtitle} {author} {publisher} {back_text}")
        self.font = QComboBox()
        self.font.setEditable(True)
        self.font.addItems(list(LOGICAL_FAMILIES) + fonts.installed_families())
        self.size = self._spin(5, 200, " pt")
        self.bold = QCheckBox("Bold")
        self.italic = QCheckBox("Italic")
        self.upper = QCheckBox("UPPERCASE")
        self.autofit = QCheckBox("Shrink to fit the box")
        self.shadow = QCheckBox("Shadow")
        self.tcolor = QPushButton()
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right"])
        self.valign = QComboBox()
        self.valign.addItems(["top", "middle", "bottom"])
        self.lh = self._spin(80, 300, "%")
        for label, w in (("Text", self.text), ("Font", self.font), ("Size", self.size), ("Colour", self.tcolor),
                         ("Align", self.align), ("Vertical", self.valign), ("Line height", self.lh)):
            tf.addRow(label, w)
        for w in (self.bold, self.italic, self.upper, self.autofit, self.shadow):
            tf.addRow("", w)
        f.addRow(self.t_group)
        self.text.textChanged.connect(lambda: self._set(text=self.text.toPlainText()))
        self.font.activated.connect(lambda _: self._set(font_family=self.font.currentText()))
        self.font.lineEdit().editingFinished.connect(lambda: self._set(font_family=self.font.currentText()))
        self.size.valueChanged.connect(lambda v: self._set(size=v))
        self.bold.toggled.connect(lambda v: self._set(bold=v))
        self.italic.toggled.connect(lambda v: self._set(italic=v))
        self.upper.toggled.connect(lambda v: self._set(uppercase=v))
        self.autofit.toggled.connect(lambda v: self._set(autofit=v))
        self.shadow.toggled.connect(lambda v: self._set(shadow=v))
        self.align.activated.connect(lambda _: self._set(align=self.align.currentText()))
        self.valign.activated.connect(lambda _: self._set(valign=self.valign.currentText()))
        self.lh.valueChanged.connect(lambda v: self._set(line_height=v / 100.0))
        self.tcolor.clicked.connect(lambda: self._pick_layer_color("color", self.tcolor))
        # shape
        self.s_group = QGroupBox("Shape")
        sf = QFormLayout(self.s_group)
        self.fill = QPushButton()
        self.fill2 = QPushButton()
        self.use_fill2 = QCheckBox("Vertical gradient to")
        self.stroke = QPushButton()
        self.no_stroke = QCheckBox("Outline")
        self.sw = self._spin(0, 40, " pt")
        self.radius = self._spin(0, 200, " pt")
        sf.addRow("Fill", self.fill)
        sf.addRow(self.use_fill2, self.fill2)
        sf.addRow(self.no_stroke, self.stroke)
        sf.addRow("Outline width", self.sw)
        sf.addRow("Corner radius", self.radius)
        f.addRow(self.s_group)
        self.fill.clicked.connect(lambda: self._pick_layer_color("fill", self.fill))
        self.fill2.clicked.connect(lambda: self._pick_layer_color("fill2", self.fill2))
        self.stroke.clicked.connect(lambda: self._pick_layer_color("stroke", self.stroke))
        self.use_fill2.toggled.connect(lambda v: self._set(fill2=(self.current_layer().fill2 or "#000000") if v else None))
        self.no_stroke.toggled.connect(lambda v: self._set(stroke=(self.current_layer().stroke or "#FFFFFF") if v else None))
        self.sw.valueChanged.connect(lambda v: self._set(stroke_width=v))
        self.radius.valueChanged.connect(lambda v: self._set(radius=v))
        # pattern
        self.p_group = QGroupBox("Pattern")
        pf = QFormLayout(self.p_group)
        self.pattern = QComboBox()
        self.pattern.addItems(PATTERNS)
        self.pscale = self._spin(4, 200, " pt")
        pf.addRow("Pattern", self.pattern)
        pf.addRow("Cell size", self.pscale)
        f.addRow(self.p_group)
        self.pattern.activated.connect(lambda _: self._set(pattern=self.pattern.currentText()))
        self.pscale.valueChanged.connect(lambda v: self._set(scale=v))
        # image
        self.i_group = QGroupBox("Image")
        imf = QFormLayout(self.i_group)
        self.img_btn = QPushButton("Choose image…")
        self.fit = QComboBox()
        self.fit.addItem("Fill (centre-crop, no distortion)", "cover")
        self.fit.addItem("Fit inside", "contain")
        self.flip = QCheckBox("Flip horizontally")
        self.fx = {}
        imf.addRow(self.img_btn)
        imf.addRow("Fit", self.fit)
        imf.addRow(self.flip)
        self.gray = QCheckBox("Black and white")
        self.sepia = QCheckBox("Sepia")
        imf.addRow(self.gray)
        imf.addRow(self.sepia)
        for key, label, lo, hi, default in (("brightness", "Brightness", 20, 200, 100), ("contrast", "Contrast", 20, 200, 100),
                                            ("saturation", "Saturation", 0, 200, 100), ("blur", "Blur", 0, 20, 0),
                                            ("tint_alpha", "Colour wash", 0, 100, 0)):
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(default)
            sl.setAccessibleName(label)
            imf.addRow(label, sl)
            self.fx[key] = (sl, default)
            sl.valueChanged.connect(lambda v, k=key: self._fx_changed(k, v))
        self.tint = QPushButton()
        imf.addRow("Wash colour", self.tint)
        self.dpi = QLabel("")
        self.dpi.setWordWrap(True)
        imf.addRow(self.dpi)
        f.addRow(self.i_group)
        self.img_btn.clicked.connect(self._choose_image)
        self.fit.activated.connect(lambda _: self._set(fit=self.fit.currentData()))
        self.flip.toggled.connect(lambda v: self._set(flip=v))
        self.gray.toggled.connect(lambda v: self._fx_bool("grayscale", v))
        self.sepia.toggled.connect(lambda v: self._fx_bool("sepia", v))
        self.tint.clicked.connect(self._pick_tint)

    def _spin(self, lo: float, hi: float, suffix: str) -> QDoubleSpinBox:
        sp = QDoubleSpinBox(minimum=lo, maximum=hi, decimals=1, singleStep=1)
        sp.setSuffix(suffix)
        return sp

    def _load_props(self) -> None:
        L = self.current_layer()
        self.props.setEnabled(L is not None)
        if L is None:
            return
        self._loading = True
        self.name.setText(L.name)
        for sp, v in ((self.x, L.x * 100), (self.y, L.y * 100), (self.w, L.w * 100), (self.h, L.h * 100),
                      (self.rot, L.rotation), (self.opacity, L.opacity * 100)):
            sp.setValue(v)
        self.locked.setChecked(L.locked)
        self.t_group.setVisible(L.kind == "text")
        self.s_group.setVisible(L.kind in ("rect", "ellipse", "line", "frame"))
        self.p_group.setVisible(L.kind == "pattern")
        self.i_group.setVisible(L.kind == "image")
        if L.kind == "text":
            self.text.setPlainText(L.text)
            self.font.setCurrentText(L.font_family)
            self.size.setValue(L.size)
            self._color_btn(self.tcolor, L.color)
            self.align.setCurrentText(L.align if L.align in ("left", "center", "right") else "left")
            self.valign.setCurrentText(L.valign)
            self.lh.setValue(L.line_height * 100)
            for w, v in ((self.bold, L.bold), (self.italic, L.italic), (self.upper, L.uppercase),
                         (self.autofit, L.autofit), (self.shadow, L.shadow)):
                w.setChecked(v)
        elif L.kind in ("rect", "ellipse", "line", "frame"):
            self._color_btn(self.fill, L.fill)
            self.use_fill2.setChecked(bool(L.fill2))
            self._color_btn(self.fill2, L.fill2)
            self.no_stroke.setChecked(bool(L.stroke))
            self._color_btn(self.stroke, L.stroke)
            self.sw.setValue(L.stroke_width)
            self.radius.setValue(L.radius)
            self.s_group.setTitle("Line" if L.kind == "line" else "Shape")
        elif L.kind == "pattern":
            self.pattern.setCurrentText(L.pattern)
            self.pscale.setValue(L.scale)
        elif L.kind == "image":
            self.fit.setCurrentIndex(0 if L.fit == "cover" else 1)
            self.flip.setChecked(L.flip)
            self.gray.setChecked(bool(L.fx.get("grayscale")))
            self.sepia.setChecked(bool(L.fx.get("sepia")))
            for k, (sl, default) in self.fx.items():
                v = L.fx.get(k)
                sl.setValue(int(round((v if v is not None else default / 100.0) * (100 if k not in ("blur",) else 1))))
            self._color_btn(self.tint, L.fx.get("tint", "#000000"))
            self._dpi_note(L)
        self._loading = False

    def _dpi_note(self, L: CoverLayer) -> None:
        a = self.book.assets.get(L.asset)
        if not a or not a.data:
            self.dpi.setText("No image chosen." if not L.asset else "Image file is missing.")
            return
        W, H = self.book.settings.page_size_pt()
        dpi = effective_dpi(a, L.w * W)
        ok = dpi >= 300
        self.dpi.setText(f"{a.width}×{a.height} px = {dpi:.0f} dpi at this size "
                         + ("— good for print." if ok else "— below 300 dpi; may print soft."))
        self.dpi.setStyleSheet(f"color: {theme.OK if ok else theme.WARNING};")

    def _set(self, **attrs) -> None:
        L = self.current_layer()
        if self._loading or L is None:
            return
        for k, v in attrs.items():
            setattr(L, k, v)
        if "name" in attrs or "text" in attrs:
            row = self.layer_list.currentRow()
            it = self.layer_list.item(row)
            if it:
                self._loading = True
                it.setText(f"{KIND_LABEL.get(L.kind, L.kind)} – {L.name or L.text[:18] or L.kind}"
                           + ("  \U0001F512" if L.locked else ""))
                self._loading = False
        self.canvas.refresh()
        if L.kind == "image":
            self._dpi_note(L)

    def _pick_layer_color(self, attr: str, btn: QPushButton) -> None:
        L = self.current_layer()
        if L is None:
            return
        c = QColorDialog.getColor(QColor(getattr(L, attr) or "#000000"), self, "Colour")
        if c.isValid():
            self._set(**{attr: c.name()})
            self._color_btn(btn, c.name())
            if attr == "fill2":
                self.use_fill2.setChecked(True)
            if attr == "stroke":
                self.no_stroke.setChecked(True)

    def _fx_changed(self, key: str, v: int) -> None:
        L = self.current_layer()
        if self._loading or L is None:
            return
        L.fx[key] = v if key == "blur" else v / 100.0
        self._set()

    def _fx_bool(self, key: str, on: bool) -> None:
        L = self.current_layer()
        if self._loading or L is None:
            return
        L.fx[key] = on
        self._set()

    def _pick_tint(self) -> None:
        L = self.current_layer()
        if L is None:
            return
        c = QColorDialog.getColor(QColor(L.fx.get("tint", "#000000")), self, "Wash colour")
        if c.isValid():
            L.fx["tint"] = c.name()
            self._color_btn(self.tint, c.name())
            self._set()

    def _choose_image(self) -> None:
        blk = choose_and_add_image(self, self.state.project)
        if blk:
            self.book.assets[blk.asset] = self.state.project.assets[blk.asset]
            self._set(asset=blk.asset)

    def _canvas_edited(self) -> None:
        self._load_props()

    # ---------------------------------------------------------------- exports
    def _build_export_box(self) -> QGroupBox:
        box = QGroupBox("Spine and export")
        lay = QFormLayout(box)
        self.thick = QDoubleSpinBox(minimum=0.01, maximum=1.0, singleStep=0.005, decimals=3, suffix=" mm",
                                    value=self.state.project.settings.paper_thickness_mm)
        self.thick.setToolTip("Thickness of ONE leaf (two pages) of your paper, as stated by your printer")
        self.spine = QLabel("")
        self.spine.setWordWrap(True)
        theme.set_muted(self.spine)
        self.thick.valueChanged.connect(self._update_spine)
        lay.addRow("Paper thickness / leaf", self.thick)
        lay.addRow(self.spine)
        self.export_btn = QPushButton("Export cover artwork…")
        menu = QMenu(self)
        menu.addAction("Digital front cover – PNG", self.export_png)
        menu.addAction("Digital front cover – PDF", lambda: self._export_pdf("front", "digital"))
        menu.addAction("Print front + back (bleed, crop marks) – PDF", lambda: self._export_pdf("front_back", "print"))
        menu.addAction("Print wrap-around cover (back + spine + front) – PDF", lambda: self._export_pdf("wrap", "print"))
        self.export_btn.setMenu(menu)
        lay.addRow(self.export_btn)
        self._update_spine()
        return box

    def interior_pages(self) -> int:
        lay = self.state.layout
        return sum(1 for p in lay.pages if not p.full_bleed) if lay else 0

    def spine_mm(self) -> float:
        return spine_width_mm(self.interior_pages(), self.thick.value())

    def _update_spine(self) -> None:
        n = self.interior_pages()
        if n:
            self.spine.setText(f"Estimated spine for {n} interior pages: {self.spine_mm():.1f} mm "
                               "(pages ÷ 2 × leaf thickness). Printers differ — confirm the "
                               "width and their cover template before ordering.")
        else:
            self.spine.setText("Spine width appears once the book has pages.")

    def export_png(self, path: str | None = None, dpi: int = 300) -> str | None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Export front cover", "front-cover.png", "PNG (*.png)")
        if not path:
            return None
        W, H = self.book.settings.page_size_pt()
        page = Page(0, W, H, "recto", (0, 0, W, H), items=cover_items(self.book, W, H, False), full_bleed=True)
        render_page(page, self.book.assets, dpi / 72.0).save(path)
        return path

    def _export_pdf(self, kind: str, profile: str, path: str | None = None) -> str | None:
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Export cover artwork", f"cover-{kind}.pdf", "PDF (*.pdf)",
                                                  options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return None
        self.book.settings.paper_thickness_mm = self.thick.value()
        self.book.settings.bleed_mm = self.state.project.settings.bleed_mm
        try:
            export_cover_pdf(self.book, Path(path), kind, profile, self.spine_mm(), overwrite=False)
        except CoverExportError as e:
            if "already exists" in str(e) and QMessageBox.question(
                    self, "Replace file", f"{Path(path).name} exists. Replace it?") == QMessageBox.Yes:
                export_cover_pdf(self.book, Path(path), kind, profile, self.spine_mm(), overwrite=True)
            else:
                QMessageBox.warning(self, "Cover export", str(e))
                return None
        return path

    # -------------------------------------------------------------------- done
    def _ok(self) -> None:
        d = self.design
        thick = self.thick.value()
        # keep the simple fields in step with the layers so other tools stay consistent
        for L in d.front_layers:
            if L.role == "title" and L.kind == "text":
                d.title_color, d.font_family = L.color, L.font_family
            if L.role == "author" and L.kind == "text":
                d.author_color = L.color

        def fn(p) -> None:
            p.settings.cover = CoverDesign.from_dict(d.to_dict())
            p.settings.paper_thickness_mm = thick
        self.state.edit("Change cover", fn, kind="settings")
        self.accept()
