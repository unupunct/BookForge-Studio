"""Paints a layout Page with QPainter. Draws the shared layout model, nothing else."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QImage, QLinearGradient, QPainter, QPen)

from ...domain.book import Asset
from ...layout.model import Glyphs, ImageItem, LineItem, Page, RectItem
from ...layout.typography import fonts

_loaded: dict[str, str] = {}
_image_cache: dict[str, QImage] = {}


def qfont_for(key: str, size: float, word_space: float = 0.0, scale: float = 1.0) -> QFont:
    face = fonts.by_key(key)
    family = None
    if face is not None:
        path = str(face.path)
        if path not in _loaded:
            fid = QFontDatabase.addApplicationFont(path)
            fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            _loaded[path] = fams[0] if fams else face.family
        family = _loaded[path]
    f = QFont(family or "Georgia")
    f.setPointSizeF(size)  # device is set to 72*scale dpi, so 1 pt == `scale` pixels
    if face is not None:
        f.setBold(face.bold)
        f.setItalic(face.italic)
    if word_space:
        f.setWordSpacing(word_space * scale)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def _asset_image(asset: Asset) -> QImage:
    img = _image_cache.get(asset.sha256 or asset.id)
    if img is None:
        img = QImage.fromData(asset.data)
        if len(_image_cache) > 32:
            _image_cache.clear()
        _image_cache[asset.sha256 or asset.id] = img
    return img


def render_page(page: Page, assets: dict[str, Asset], scale: float = 1.0,
                paper: str = "#FFFFFF") -> QImage:
    w, h = max(int(round(page.width * scale)), 1), max(int(round(page.height * scale)), 1)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor(paper))
    dpm = int(72.0 * scale / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
    for it in page.all_items():
        _draw(p, it, assets, scale)
    p.end()
    return img


def _draw(p: QPainter, it, assets: dict[str, Asset], s: float) -> None:
    if isinstance(it, RectItem):
        r = QRectF(it.x * s, it.y * s, it.w * s, it.h * s)
        if it.fill and it.gradient_to:
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(it.fill))
            g.setColorAt(1, QColor(it.gradient_to))
            p.fillRect(r, g)
        elif it.fill:
            p.fillRect(r, QColor(it.fill))
        if it.stroke:
            p.setPen(QPen(QColor(it.stroke), max(it.stroke_width * s, 0.5)))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
    elif isinstance(it, LineItem):
        p.setPen(QPen(QColor(it.color), max(it.width * s, 0.5)))
        p.drawLine(QPointF(it.x1 * s, it.y1 * s), QPointF(it.x2 * s, it.y2 * s))
    elif isinstance(it, Glyphs):
        if not it.text:
            return
        p.setFont(qfont_for(it.font, it.size, it.word_space, s))
        p.setPen(QColor(it.color))
        p.drawText(QPointF(it.x * s, it.y * s), it.text)
        if it.underline:
            p.setPen(QPen(QColor(it.color), max(it.size * 0.05 * s, 0.5)))
            y = (it.y + it.size * 0.12) * s
            p.drawLine(QPointF(it.x * s, y), QPointF((it.x + it.width) * s, y))
    elif isinstance(it, ImageItem):
        asset = assets.get(it.asset_id)
        target = QRectF(it.x * s, it.y * s, it.w * s, it.h * s)
        if asset is None or not asset.data:
            return
        img = _asset_image(asset)
        if img.isNull():
            return
        src = QRectF(0, 0, img.width(), img.height())
        if it.crop:
            l, t, r, b = it.crop
            src = QRectF(l * img.width(), t * img.height(), (r - l) * img.width(),
                         (b - t) * img.height())
        p.drawImage(target, img, src)


def block_bbox(page: Page, block_id: str) -> QRectF | None:
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for it in page.items:
        if getattr(it, "block_id", None) != block_id:
            continue
        if isinstance(it, Glyphs):
            bx0, by0, bx1, by1 = it.x, it.y - it.size * 0.85, it.x + it.width, it.y + it.size * 0.3
        elif isinstance(it, (RectItem, ImageItem)):
            bx0, by0, bx1, by1 = it.x, it.y, it.x + it.w, it.y + it.h
        else:
            continue
        x0, y0, x1, y1 = min(x0, bx0), min(y0, by0), max(x1, bx1), max(y1, by1)
    if x1 < x0:
        return None
    return QRectF(x0, y0, x1 - x0, y1 - y0)


def block_at(page: Page, x: float, y: float) -> str | None:
    """Block id under a point in page coordinates (points)."""
    for it in reversed(page.items):
        bid = getattr(it, "block_id", None)
        if not bid:
            continue
        if isinstance(it, Glyphs):
            if it.x <= x <= it.x + it.width and it.y - it.size <= y <= it.y + it.size * 0.4:
                return bid
        elif isinstance(it, ImageItem):
            if it.x <= x <= it.x + it.w and it.y <= y <= it.y + it.h:
                return bid
    return None
