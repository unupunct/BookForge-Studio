"""Page preview: thumbnails, single page and two-page spread, zoom, issue highlighting."""
from __future__ import annotations

from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
                               QToolButton, QVBoxLayout, QWidget)

from ...application_state import AppState
from ...layout.model import LayoutResult, Page
from .. import theme
from .page_renderer import block_at, block_bbox, render_page

ZOOMS = ["Fit width", "Fit page", "50%", "75%", "100%", "125%", "150%", "200%"]
SCREEN_SCALE = 96.0 / 72.0  # 100% zoom: one point == one CSS pixel at 96 dpi


class PageCanvas(QWidget):
    block_clicked = Signal(str, int)

    def __init__(self, panel: "PreviewPanel"):
        super().__init__()
        self.panel = panel
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setAccessibleName("Page preview")

    def pages_shown(self) -> list[Page]:
        return self.panel.visible_pages()

    def sizeHint(self) -> QSize:
        pages = self.pages_shown()
        s = self.panel.scale()
        if not pages:
            return QSize(200, 200)
        w = sum(int(p.width * s) for p in pages) + 2 * 24
        h = int(max(p.height for p in pages) * s) + 2 * 24
        return QSize(w, h)

    def _rects(self) -> list[tuple[Page, QRectF]]:
        s = self.panel.scale()
        x = 24.0
        out = []
        for p in self.pages_shown():
            out.append((p, QRectF(x, 24, p.width * s, p.height * s)))
            x += p.width * s
        return out

    def paintEvent(self, e) -> None:
        pt = QPainter(self)
        pt.fillRect(self.rect(), QColor(theme.BG))
        s = self.panel.scale()
        for page, rect in self._rects():
            # soft shadow
            pt.fillRect(rect.translated(4, 5), QColor(0, 0, 0, 90))
            img = self.panel.page_image(page, s)
            pt.drawImage(rect.topLeft(), img)
            hl = self.panel.highlight_block
            if hl:
                bb = block_bbox(page, hl)
                if bb:
                    r = QRectF(rect.x() + bb.x() * s - 3, rect.y() + bb.y() * s - 3,
                               bb.width() * s + 6, bb.height() * s + 6)
                    pt.fillRect(r, QColor(208, 140, 75, 60))
                    pt.setPen(QPen(QColor(theme.ACCENT), 2))
                    pt.drawRect(r)
            issues = self.panel.page_issues(page.index)
            if issues:
                sev = "error" if any(i.severity == "error" for i in issues) else "warning"
                col = QColor(theme.ERROR if sev == "error" else theme.WARNING)
                pt.setPen(QPen(col, 2))
                pt.drawRect(rect.adjusted(1, 1, -1, -1))
                pt.fillRect(QRectF(rect.right() - 74, rect.y(), 74, 20), col)
                pt.setPen(QColor("#1B1C1F"))
                pt.drawText(QRectF(rect.right() - 74, rect.y(), 74, 20), Qt.AlignCenter,
                            f"⚠ {len(issues)} issue{'s' if len(issues) != 1 else ''}")
        pt.end()

    def mousePressEvent(self, e) -> None:
        pos = e.position()
        s = self.panel.scale()
        for page, rect in self._rects():
            if rect.contains(pos):
                bid = block_at(page, (pos.x() - rect.x()) / s, (pos.y() - rect.y()) / s)
                if bid:
                    self.block_clicked.emit(bid, page.index)
                return

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        s = self.panel.scale()
        cur = Qt.ArrowCursor
        for page, rect in self._rects():
            if rect.contains(pos) and block_at(page, (pos.x() - rect.x()) / s,
                                                (pos.y() - rect.y()) / s):
                cur = Qt.PointingHandCursor
        self.setCursor(cur)
        issues = []
        for page, rect in self._rects():
            if rect.contains(pos):
                issues = self.panel.page_issues(page.index)
        self.setToolTip("\n".join(f"{i.severity.upper()}: {i.message}" for i in issues[:6]))


class PreviewPanel(QWidget):
    block_requested = Signal(str)        # user clicked a block in the preview
    page_changed = Signal(int)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.layout_result: LayoutResult | None = None
        self.current = 0
        self.highlight_block: str | None = None
        self._cache: OrderedDict[tuple, QImage] = OrderedDict()
        self._issues_by_page: dict[int, list] = {}
        self._thumb_queue: list[int] = []
        self._zoom_text = "Fit width"
        self._spread = False

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 6)
        self.prev_btn = QToolButton(text="◀")
        self.prev_btn.setToolTip("Previous page (Page Up)")
        self.next_btn = QToolButton(text="▶")
        self.next_btn.setToolTip("Next page (Page Down)")
        self.spin = QSpinBox(minimum=1, maximum=1)
        self.spin.setAccessibleName("Page number")
        self.total = QLabel("/ 0")
        self.mode = QComboBox()
        self.mode.addItems(["Single page", "Two-page spread"])
        self.mode.setToolTip("Single page or facing-page spread")
        self.zoom = QComboBox()
        self.zoom.addItems(ZOOMS)
        self.zoom.setToolTip("Zoom (Ctrl + mouse wheel)")
        self.issue_btn = QPushButton("Next issue")
        self.issue_btn.setToolTip("Jump to the next page with a layout problem")
        self.status = QLabel("")
        theme.set_muted(self.status)
        for w in (self.prev_btn, self.spin, self.total, self.next_btn, self.mode, self.zoom,
                  self.issue_btn):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self.status)

        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListWidget.IconMode)
        self.thumbs.setIconSize(QSize(84, 118))
        self.thumbs.setResizeMode(QListWidget.Adjust)
        self.thumbs.setMovement(QListWidget.Static)
        self.thumbs.setWrapping(False)
        self.thumbs.setFlow(QListWidget.TopToBottom)
        self.thumbs.setSpacing(6)
        self.thumbs.setFixedWidth(118)
        self.thumbs.setAccessibleName("Page thumbnails")
        self.canvas = PageCanvas(self)
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {theme.BG}; border: 0; }}")

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.thumbs)
        body.addWidget(self.scroll, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addLayout(body, 1)

        self.prev_btn.clicked.connect(lambda: self.go_relative(-1))
        self.next_btn.clicked.connect(lambda: self.go_relative(1))
        self.spin.valueChanged.connect(lambda v: self.show_page(v - 1, from_spin=True))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.zoom.currentTextChanged.connect(self._zoom_changed)
        self.thumbs.currentRowChanged.connect(self._thumb_selected)
        self.issue_btn.clicked.connect(self.next_issue)
        self.canvas.block_clicked.connect(lambda b, i: self.block_requested.emit(b))
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(15)
        self._thumb_timer.timeout.connect(self._fill_thumbs)
        self.scroll.viewport().installEventFilter(self)
        state.layout_ready.connect(self.set_layout)

    # ------------------------------------------------------------- data
    def set_layout(self, result: LayoutResult) -> None:
        first = self.layout_result is None
        self.layout_result = result
        self._cache.clear()
        self._issues_by_page.clear()
        for i in result.issues:
            if i.page_index is not None and i.severity in ("error", "warning"):
                self._issues_by_page.setdefault(i.page_index, []).append(i)
        n = result.page_count
        self.spin.blockSignals(True)
        self.spin.setMaximum(max(n, 1))
        self.spin.blockSignals(False)
        self.total.setText(f"/ {n}")
        self.current = min(self.current, max(n - 1, 0))
        self._rebuild_thumbs()
        self._refresh()
        n_issues = sum(len(v) for v in self._issues_by_page.values())
        self.status.setText(f"{n} pages" + (f" • {n_issues} layout issue(s)" if n_issues else ""))
        self.issue_btn.setEnabled(bool(self._issues_by_page))

    def page_issues(self, index: int) -> list:
        return self._issues_by_page.get(index, [])

    # ------------------------------------------------------------ geometry
    def visible_pages(self) -> list[Page]:
        r = self.layout_result
        if not r or not r.pages:
            return []
        cur = r.pages[min(self.current, r.page_count - 1)]
        if not self._spread or not self.state.project.settings.facing_pages:
            return [cur]
        if cur.index == 0:
            return [cur]
        partner = cur.index - 1 if cur.side == "recto" else cur.index + 1
        if 0 < partner < r.page_count:
            pair = sorted([cur, r.pages[partner]], key=lambda p: p.index)
            return pair
        return [cur]

    def scale(self) -> float:
        z = self._zoom_text
        r = self.layout_result
        if not r or not r.pages:
            return SCREEN_SCALE
        pages = self.visible_pages() or [r.pages[0]]
        total_w = sum(p.width for p in pages)
        max_h = max(p.height for p in pages)
        vp = self.scroll.viewport().size()
        if z == "Fit width":
            return max((vp.width() - 56) / total_w, 0.1)
        if z == "Fit page":
            return max(min((vp.width() - 56) / total_w, (vp.height() - 56) / max_h), 0.1)
        return int(z.rstrip("%")) / 100.0 * SCREEN_SCALE

    def page_image(self, page: Page, scale: float) -> QImage:
        key = (page.index, round(scale, 3))
        img = self._cache.get(key)
        if img is None:
            img = render_page(page, self.state.project.assets, scale)
            self._cache[key] = img
            while len(self._cache) > 24:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return img

    def _refresh(self) -> None:
        self.canvas.resize(self.canvas.sizeHint())
        self.canvas.update()
        self.spin.blockSignals(True)
        self.spin.setValue(self.current + 1)
        self.spin.blockSignals(False)
        self.thumbs.blockSignals(True)
        self.thumbs.setCurrentRow(self.current)
        self.thumbs.blockSignals(False)
        r = self.layout_result
        if r and r.pages:
            self.prev_btn.setEnabled(self.current > 0)
            self.next_btn.setEnabled(self.current < r.page_count - 1)

    # ------------------------------------------------------------ navigation
    def show_page(self, index: int, from_spin: bool = False) -> None:
        r = self.layout_result
        if not r or not r.pages:
            return
        index = max(0, min(index, r.page_count - 1))
        changed = index != self.current
        self.current = index
        self._refresh()
        self.scroll.verticalScrollBar().setValue(0)
        if changed:
            self.page_changed.emit(index)

    def go_relative(self, delta: int) -> None:
        step = delta
        if self._spread and self.layout_result and delta and self.current + delta > 0:
            step = 2 * delta if len(self.visible_pages()) == 2 else delta
        self.show_page(self.current + step)

    def show_block(self, block_id: str | None) -> bool:
        self.highlight_block = block_id
        r = self.layout_result
        if block_id and r and block_id in r.block_pages:
            self.show_page(r.block_pages[block_id][0])
            self.canvas.update()
            return True
        self.canvas.update()
        return False

    def show_section(self, section_id: str) -> None:
        r = self.layout_result
        if r and section_id in r.section_pages:
            self.show_page(r.section_pages[section_id])

    def next_issue(self) -> None:
        pages = sorted(self._issues_by_page)
        if not pages:
            return
        nxt = next((p for p in pages if p > self.current), pages[0])
        self.show_page(nxt)

    def _mode_changed(self, idx: int) -> None:
        self._spread = idx == 1
        self._cache.clear()
        self._refresh()

    def _zoom_changed(self, text: str) -> None:
        self._zoom_text = text
        self._refresh()

    def _thumb_selected(self, row: int) -> None:
        if row >= 0 and row != self.current:
            self.show_page(row)

    def eventFilter(self, obj, ev) -> bool:
        from PySide6.QtCore import QEvent
        try:
            return self._event_filter(obj, ev, QEvent)
        except RuntimeError:  # widgets already destroyed during shutdown
            return False

    def _event_filter(self, obj, ev, QEvent) -> bool:
        if obj is self.scroll.viewport() and ev.type() == QEvent.Wheel and \
                ev.modifiers() & Qt.ControlModifier:
            idx = ZOOMS.index(self._zoom_text) if self._zoom_text in ZOOMS else 4
            idx = max(2, min(len(ZOOMS) - 1, idx + (1 if ev.angleDelta().y() > 0 else -1)))
            self.zoom.setCurrentIndex(idx)
            return True
        if obj is self.scroll.viewport() and ev.type() == QEvent.Resize and \
                self._zoom_text in ("Fit width", "Fit page"):
            QTimer.singleShot(0, self._refresh)
        return super().eventFilter(obj, ev)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_PageDown:
            self.go_relative(1)
        elif e.key() == Qt.Key_PageUp:
            self.go_relative(-1)
        else:
            super().keyPressEvent(e)

    # -------------------------------------------------------------- thumbnails
    def _rebuild_thumbs(self) -> None:
        r = self.layout_result
        self.thumbs.blockSignals(True)
        self.thumbs.clear()
        if r:
            ph = QPixmap(84, 118)
            ph.fill(QColor(theme.SURFACE))
            for p in r.pages:
                label = p.label or ("–" if p.blank else "·")
                it = QListWidgetItem(QIcon(ph), f"{p.index + 1}  ({label})" if p.label else f"{p.index + 1}")
                it.setTextAlignment(Qt.AlignHCenter)
                self.thumbs.addItem(it)
            self._thumb_queue = list(range(r.page_count))
            self._thumb_timer.start()
        self.thumbs.blockSignals(False)

    def _fill_thumbs(self) -> None:
        r = self.layout_result
        if not r or not self._thumb_queue:
            self._thumb_timer.stop()
            return
        for _ in range(4):
            if not self._thumb_queue:
                break
            i = self._thumb_queue.pop(0)
            if i >= len(r.pages):
                continue
            p = r.pages[i]
            scale = 118.0 / p.height
            img = render_page(p, self.state.project.assets, scale)
            item = self.thumbs.item(i)
            if item:
                item.setIcon(QIcon(QPixmap.fromImage(img)))
