"""PDF rendering of a LayoutResult with ReportLab.

The exporter performs no layout of its own: it draws exactly what the shared
layout model describes.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from ..domain.book import BookProject
from ..domain.layouts import MM_TO_PT
from ..layout.model import Glyphs, ImageItem, LayoutResult, LineItem, Page, RectItem
from ..layout.typography import fonts as font_manager
from ..services.image_service import prepare_image


@dataclass(frozen=True)
class PdfProfile:
    key: str
    label: str
    bleed_mm: float = 0.0
    crop_marks: bool = False
    image_dpi: int = 200
    jpeg_quality: int = 85
    show_boundaries: bool = False
    diagnostics: bool = False
    description: str = ""


PROFILES: dict[str, PdfProfile] = {
    "digital": PdfProfile("digital", "Digital PDF", 0.0, False, 150, 82,
                          description="Screen reading: searchable text, bookmarks and links, "
                                      "moderate file size, no bleed."),
    "print": PdfProfile("print", "Print PDF", 3.0, True, 300, 92,
                        description="Trim size plus bleed, optional crop marks and "
                                    "high-resolution images. Not PDF/X certified."),
    "proof": PdfProfile("proof", "Proof PDF", 0.0, False, 96, 60, show_boundaries=True,
                        diagnostics=True,
                        description="Fast review copy with page boundaries and diagnostics."),
}

SLUG_PT = 9 * MM_TO_PT  # room for crop marks beyond the bleed


class ExportCancelled(Exception):
    pass


def _color(c: str | None):
    return HexColor(c) if c else None


def _is_full_page(r: RectItem, W: float, H: float) -> bool:
    return r.x <= 0.5 and r.y <= 0.5 and r.w >= W - 1 and r.h >= H - 1


def render_pdf(book: BookProject, layout: LayoutResult, path: Path, profile: PdfProfile,
               bleed_mm: float | None = None, crop_marks: bool | None = None,
               progress: Callable[[int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None) -> dict:
    """Write the PDF to `path`. Returns geometry information used for verification."""
    W, H = layout.page_width, layout.page_height
    bleed = (profile.bleed_mm if bleed_mm is None else bleed_mm) * MM_TO_PT
    marks = profile.crop_marks if crop_marks is None else crop_marks
    ofs = bleed + (SLUG_PT if marks and bleed > 0 else 0.0)
    if marks and bleed == 0:
        ofs = SLUG_PT
    PW, PH = W + 2 * ofs, H + 2 * ofs
    md = book.metadata

    # An embedded font is the initial font so no unembedded Helvetica reference is emitted.
    base_font = font_manager.face("serif").key
    c = Canvas(str(path), pagesize=(PW, PH), pageCompression=1, invariant=0,
               initialFontName=base_font, initialFontSize=10)
    c.setTitle(md.title)
    c.setAuthor(md.author)
    c.setSubject(md.subtitle or md.description)
    c.setCreator("BookForge Studio")
    c.setProducer("BookForge Studio (ReportLab)")
    if hasattr(c, "setLang") and md.language:
        try:
            c.setLang(md.language)
        except Exception:
            pass

    outline_by_page: dict[int, list] = {}
    for e in layout.outline:
        outline_by_page.setdefault(e.page_index, []).append(e)
    all_anchors = {a for p in layout.pages for a in p.anchors}
    last_level = -1
    total = len(layout.pages)

    def py(y_top: float) -> float:
        return PH - ofs - y_top

    def draw_page(page: Page) -> None:
        nonlocal last_level
        for e_anchor, y in page.anchors.items():
            c.bookmarkHorizontal(e_anchor, ofs, py(y) + 12)
        for e in outline_by_page.get(page.index, []):
            level = min(max(e.level - 1, 0), last_level + 1)
            c.addOutlineEntry(e.title, e.anchor, level=level, closed=False)
            last_level = level
        for it in page.all_items():
            if isinstance(it, RectItem):
                x, y, w, h = it.x, it.y, it.w, it.h
                if page.full_bleed and _is_full_page(it, W, H):
                    x, y, w, h = -bleed, -bleed, W + 2 * bleed, H + 2 * bleed
                if it.gradient_to and it.fill:
                    c.saveState()
                    p = c.beginPath()
                    p.rect(ofs + x, py(y + h), w, h)
                    c.clipPath(p, stroke=0, fill=0)
                    c.linearGradient(ofs + x, py(y), ofs + x, py(y + h),
                                     (HexColor(it.fill), HexColor(it.gradient_to)))
                    c.restoreState()
                    continue
                if it.fill is None and it.stroke is None:
                    continue
                c.saveState()
                if it.fill:
                    c.setFillColor(HexColor(it.fill))
                if it.stroke:
                    c.setStrokeColor(HexColor(it.stroke))
                    c.setLineWidth(it.stroke_width)
                c.rect(ofs + x, py(y + h), w, h, stroke=1 if it.stroke else 0,
                       fill=1 if it.fill else 0)
                c.restoreState()
            elif isinstance(it, LineItem):
                c.saveState()
                c.setStrokeColor(HexColor(it.color))
                c.setLineWidth(it.width)
                c.line(ofs + it.x1, py(it.y1), ofs + it.x2, py(it.y2))
                c.restoreState()
            elif isinstance(it, Glyphs):
                if not it.text:
                    continue
                t = c.beginText(ofs + it.x, py(it.y))
                t.setFont(it.font, it.size)
                t.setFillColor(HexColor(it.color))
                if it.word_space:
                    t.setWordSpace(it.word_space)
                t.textOut(it.text)
                c.drawText(t)
                if it.underline:
                    c.saveState()
                    c.setStrokeColor(HexColor(it.color))
                    c.setLineWidth(max(it.size * 0.05, 0.3))
                    c.line(ofs + it.x, py(it.y) - it.size * 0.12, ofs + it.x + it.width,
                           py(it.y) - it.size * 0.12)
                    c.restoreState()
                if it.link:
                    rect = (ofs + it.x, py(it.y) - it.size * 0.25, ofs + it.x + it.width,
                            py(it.y) + it.size * 0.8)
                    if it.link.startswith("#"):
                        if it.link[1:] in all_anchors:
                            c.linkRect("", it.link[1:], rect, relative=0, thickness=0)
                    elif it.link.lower().startswith(("http://", "https://", "mailto:")):
                        c.linkURL(it.link, rect, relative=0, thickness=0)
            elif isinstance(it, ImageItem):
                asset = book.assets.get(it.asset_id)
                if asset is None or not asset.data:
                    continue
                data, _fmt = prepare_image(asset, it.crop, it.w, profile.image_dpi,
                                           profile.jpeg_quality)
                x, y, w, h = it.x, it.y, it.w, it.h
                if page.full_bleed and x <= 0.5 and y <= 0.5 and w >= W - 1 and h >= H - 1:
                    x, y, w, h = -bleed, -bleed, W + 2 * bleed, H + 2 * bleed
                c.drawImage(ImageReader(io.BytesIO(data)), ofs + x, py(y + h), w, h, mask="auto")

    def draw_marks() -> None:
        c.saveState()
        c.setStrokeColor(HexColor("#000000"))
        c.setLineWidth(0.25)
        gap, ln = bleed + 2, 6 * MM_TO_PT
        for cx in (ofs, ofs + W):
            sx = -1 if cx == ofs else 1
            for cy in (ofs, ofs + H):
                sy = -1 if cy == ofs else 1
                c.line(cx + sx * gap, cy, cx + sx * (gap + ln), cy)
                c.line(cx, cy + sy * gap, cx, cy + sy * (gap + ln))
        c.restoreState()

    for page in layout.pages:
        if cancel and cancel():
            c.save()
            raise ExportCancelled()
        c.setPageSize((PW, PH))
        try:  # page boxes make the trim and bleed explicit for printers
            c.setTrimBox((ofs, ofs, ofs + W, ofs + H))
            c.setBleedBox((ofs - bleed, ofs - bleed, ofs + W + bleed, ofs + H + bleed))
        except Exception:
            pass
        draw_page(page)
        if profile.show_boundaries:
            c.saveState()
            c.setStrokeColor(HexColor("#E04040"))
            c.setLineWidth(0.4)
            c.rect(ofs, ofs, W, H)
            x0, y0, x1, y1 = page.content_box
            c.setStrokeColor(HexColor("#4080E0"))
            c.setDash(2, 2)
            c.rect(ofs + x0, py(y1), x1 - x0, y1 - y0)
            c.restoreState()
        if profile.diagnostics:
            c.saveState()
            c.setFont(font_manager.face("sans").key, 6)
            c.setFillColor(HexColor("#E04040"))
            n_issues = sum(1 for i in layout.issues if i.page_index == page.index)
            note = f"PROOF  p{page.index + 1}/{total}  label={page.label or '-'}  {page.side}  issues={n_issues}"
            c.drawString(ofs + 4, 4, note)
            c.restoreState()
        if marks:
            draw_marks()
        c.showPage()
        if progress:
            progress(page.index + 1, total)
    c.save()
    return {"page_width": PW, "page_height": PH, "trim_width": W, "trim_height": H,
            "bleed_pt": bleed, "offset_pt": ofs}
