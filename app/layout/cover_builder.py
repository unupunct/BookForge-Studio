"""Turns layered cover designs into layout items (shared by preview, PNG and PDF export)."""
from __future__ import annotations

import math

from ..domain.book import BookProject
from ..domain.layouts import CoverDesign, CoverLayer
from ..domain.styles import ResolvedStyle
from ..domain.content_blocks import Run
from .measurement import break_lines, place_line, tokenize
from .model import Glyphs, ImageItem, Item, LineItem, RectItem
from .typography import fonts

MAX_PATTERN_ITEMS = 3500
PATTERNS = ["stripes", "dots", "grid", "waves", "circles", "triangles"]


def resolve_tokens(text: str, book: BookProject) -> str:
    md, cv = book.metadata, book.settings.cover
    return (text.replace("{title}", md.title).replace("{subtitle}", md.subtitle)
            .replace("{author}", md.author).replace("{publisher}", cv.publisher_text or md.publisher)
            .replace("{back_text}", cv.back_text))


def fx_key(fx: dict) -> tuple | None:
    return tuple(sorted((k, v) for k, v in fx.items() if v not in (None, False, 0, 0.0, 1.0, ""))) or None


def _text_items(book: BookProject, L: CoverLayer, W: float, H: float) -> list[Item]:
    box_x, box_y, box_w, box_h = L.x * W, L.y * H, L.w * W, L.h * H
    text = resolve_tokens(L.text, book)
    if not text.strip():
        return []
    size = L.size

    def lay(sz: float):
        style = ResolvedStyle("cover", font_family=L.font_family, font_size=sz, bold=L.bold,
                              italic=L.italic, color=L.color, uppercase=L.uppercase)
        lines = []
        for para in text.split("\n"):
            toks = tokenize([Run(para)], style)
            lines.extend(break_lines(toks, box_w, box_w))
        return lines, sz * L.line_height

    lines, lead = lay(size)
    if L.autofit:
        face = fonts.face(L.font_family, bold=L.bold)
        words = [w.upper() if L.uppercase else w for w in text.split()]

        def too_wide(sz: float) -> bool:  # a single word wider than the box would be broken mid-word
            return any(fonts.width(w, face.key, sz) > box_w for w in words)

        while (len(lines) * lead > box_h or too_wide(size)) and size > 6:
            size *= 0.93
            lines, lead = lay(size)
    total = len(lines) * lead
    top = box_y + {"middle": (box_h - total) / 2, "bottom": box_h - total}.get(L.valign, 0.0)
    cx, cy = box_x + box_w / 2, box_y + box_h / 2
    out: list[Item] = []
    for n, ln in enumerate(lines):
        items, _ = place_line(ln, box_x, box_w, L.align if L.align != "justify" else "left", None)
        for g in items:
            g.y += top + n * lead + size
            g.rot, g.pivot_x, g.pivot_y, g.opacity = L.rotation, cx, cy, L.opacity
            if L.shadow:
                sh = Glyphs(**{**g.__dict__, "x": g.x + size * 0.04, "y": g.y + size * 0.05,
                               "color": L.shadow_color, "opacity": L.opacity * 0.5})
                out.append(sh)
            out.append(g)
    return out


def _pattern_items(L: CoverLayer, W: float, H: float) -> list[Item]:
    """Generate the pattern; if it would exceed the item budget the cells are enlarged until it fits."""
    sc = max(L.scale, 4.0)
    while True:
        items = _pattern_at(L, W, H, sc)
        if len(items) <= MAX_PATTERN_ITEMS:
            return items
        sc *= 1.35


def _pattern_at(L: CoverLayer, W: float, H: float, sc: float) -> list[Item]:
    x0, y0, w, h = L.x * W, L.y * H, L.w * W, L.h * H
    cx, cy = x0 + w / 2, y0 + h / 2
    col = L.fill or L.stroke or "#FFFFFF"
    common = dict(rot=L.rotation, pivot_x=cx, pivot_y=cy, opacity=L.opacity)
    sw = max(L.stroke_width, 0.3)
    out: list[Item] = []
    if L.pattern == "stripes":
        y = y0
        while y <= y0 + h:
            out.append(LineItem(x0, y, x0 + w, y, sw, col, **common))
            y += sc
    elif L.pattern == "grid":
        y = y0
        while y <= y0 + h + 0.1:
            out.append(LineItem(x0, y, x0 + w, y, sw, col, **common))
            y += sc
        x = x0
        while x <= x0 + w + 0.1:
            out.append(LineItem(x, y0, x, y0 + h, sw, col, **common))
            x += sc
    elif L.pattern == "dots":
        r = sc * 0.16
        y = y0 + sc / 2
        while y < y0 + h:
            x = x0 + sc / 2
            while x < x0 + w:
                out.append(RectItem(x - r, y - r, 2 * r, 2 * r, fill=col, shape="ellipse", **common))
                x += sc
            y += sc
    elif L.pattern == "waves":
        amp = sc * 0.28
        y = y0 + sc / 2
        while y < y0 + h:
            px, py = x0, y
            x = x0 + 5
            while x <= x0 + w:
                ny = y + amp * math.sin((x - x0) / sc * 2 * math.pi)
                out.append(LineItem(px, py, x, ny, sw, col, **common))
                px, py = x, ny
                x += 5
            y += sc
    elif L.pattern == "circles":
        r = sc
        while r <= min(w, h) / 2 + 0.1:
            out.append(RectItem(cx - r, cy - r, 2 * r, 2 * r, fill=None, stroke=col, stroke_width=sw,
                                shape="ellipse", **common))
            r += sc
    elif L.pattern == "triangles":
        y = y0
        while y + sc <= y0 + h + 0.1:
            x = x0
            while x + sc <= x0 + w + 0.1:
                a, b, c = (x, y + sc), (x + sc, y + sc), (x + sc / 2, y)
                for p, q in ((a, b), (b, c), (c, a)):
                    out.append(LineItem(p[0], p[1], q[0], q[1], sw, col, **common))
                x += sc
            y += sc
    return out


def layer_items(book: BookProject, L: CoverLayer, W: float, H: float) -> list[Item]:
    if not L.visible:
        return []
    x, y, w, h = L.x * W, L.y * H, L.w * W, L.h * H
    cx, cy = x + w / 2, y + h / 2
    rot = dict(rot=L.rotation, pivot_x=cx, pivot_y=cy, opacity=L.opacity)
    if L.kind == "text":
        return _text_items(book, L, W, H)
    if L.kind == "rect":
        return [RectItem(x, y, w, h, fill=L.fill, stroke=L.stroke, stroke_width=L.stroke_width,
                         gradient_to=L.fill2, radius=L.radius, **rot)]
    if L.kind == "ellipse":
        return [RectItem(x, y, w, h, fill=L.fill, stroke=L.stroke, stroke_width=L.stroke_width,
                         gradient_to=L.fill2, shape="ellipse", **rot)]
    if L.kind == "frame":
        return [RectItem(x, y, w, h, fill=None, stroke=L.stroke or L.fill or "#FFFFFF",
                         stroke_width=L.stroke_width, radius=L.radius, **rot)]
    if L.kind == "line":
        return [LineItem(x, cy, x + w, cy, L.stroke_width, L.stroke or L.fill or "#FFFFFF", **rot)]
    if L.kind == "pattern":
        return _pattern_items(L, W, H)
    if L.kind == "image":
        asset = book.assets.get(L.asset)
        if not L.asset:  # a photo slot waiting for an image
            return [RectItem(x, y, w, h, fill="#4A4D54", **rot)]
        if asset is None or not asset.data:
            return [RectItem(x, y, w, h, fill="#555555", stroke="#B04040", **rot)]
        iw, ih = asset.width or 1, asset.height or 1
        if L.fit == "contain":
            s = min(w / iw, h / ih)
            dw, dh = iw * s, ih * s
            return [ImageItem(x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, asset.id, None, L.name,
                              flip=L.flip, fx=fx_key(L.fx), **rot)]
        target, src = w / h, iw / ih
        if src > target:
            f = target / src
            crop = ((1 - f) / 2, 0.0, (1 + f) / 2, 1.0)
        else:
            f = src / target
            crop = (0.0, (1 - f) / 2, 1.0, (1 + f) / 2)
        return [ImageItem(x, y, w, h, asset.id, crop, L.name, flip=L.flip, fx=fx_key(L.fx), **rot)]
    return []


def side_items(book: BookProject, layers: list[CoverLayer], W: float, H: float,
               background: str, background2: str | None) -> list[Item]:
    items: list[Item] = [RectItem(0, 0, W, H, fill=background, gradient_to=background2)]
    for L in layers:
        items.extend(layer_items(book, L, W, H))
    return items


def wrap_items(book: BookProject, front: list[Item], back: list[Item], W: float, H: float,
               spine: float, bleed: float = 0.0) -> list[Item]:
    """Back + spine + front as one artwork of width 2W + spine.

    With a bleed, the outer colours are extended past the trim so nothing white shows after cutting.
    """
    cv: CoverDesign = book.settings.cover
    back_bg = cv.back_background or cv.background
    spine_bg = cv.spine_color or cv.background
    items: list[Item] = []
    if bleed > 0:
        total = 2 * W + spine
        for x, w, col in ((0, W, back_bg), (W, spine, spine_bg), (W + spine, W, cv.background)):
            items.append(RectItem(x, -bleed, w, H + 2 * bleed, fill=col))
        items.append(RectItem(-bleed, -bleed, bleed, H + 2 * bleed, fill=back_bg))
        items.append(RectItem(total, -bleed, bleed, H + 2 * bleed, fill=cv.background))
    items.extend(back)
    items.append(RectItem(W, 0, spine, H, fill=spine_bg))
    items.extend(it.moved(W + spine, 0) for it in front)
    if cv.spine_text and spine >= 8:
        md = book.metadata
        cx, cy = W + spine / 2, H / 2
        size = min(spine * 0.55, 16)
        face = fonts.face(cv.font_family, bold=True)
        # Text is laid out horizontally and rotated 90 degrees clockwise about the spine centre
        # (reads top to bottom). After that rotation, +x offsets move DOWN the spine.
        for text, sz, offset, color in ((md.title, size, -H * 0.12 if md.author else 0.0, cv.title_color),
                                        (md.author, size * 0.8, H * 0.30, cv.author_color)):
            if not text:
                continue
            tw = fonts.width(text, face.key, sz)
            items.append(Glyphs(x=cx + offset - tw / 2, y=cy + sz * 0.3, text=text, font=face.key, size=sz,
                                color=color, width=tw, rot=-90, pivot_x=cx, pivot_y=cy))
    return items
