"""A reading edition for screens: phone, tablet and computer.

The print layout (facing pages, gutters, blank leaves to fill signatures) is wrong on a
screen, so the screen PDF is laid out again on a single-page format with small even
margins. The book itself is not modified: a copy with adjusted settings is returned.
A dark variant recolours the laid-out pages (light text on a dark page) for night reading.
"""
from __future__ import annotations

import colorsys
import copy
from dataclasses import dataclass, replace

from ..domain.book import BookProject
from ..domain.layouts import Margins
from ..layout.model import Glyphs, LayoutResult, LineItem, RectItem


@dataclass(frozen=True)
class ScreenSize:
    label: str
    width_mm: float
    height_mm: float
    margins: Margins
    body_pt: float


SIZES: dict[str, ScreenSize] = {
    "phone": ScreenSize("Phone (9:16)", 108.0, 192.0, Margins(top=11, bottom=13, inner=9, outer=9), 11.0),
    "tablet": ScreenSize("Tablet (3:4)", 150.0, 200.0, Margins(top=14, bottom=16, inner=13, outer=13), 11.5),
    "computer": ScreenSize("Computer (A4 page)", 210.0, 297.0, Margins(top=20, bottom=22, inner=22, outer=22), 12.0),
}
DEFAULT_SIZE = "phone"
SCREEN_WIDTH_MM, SCREEN_HEIGHT_MM = SIZES[DEFAULT_SIZE].width_mm, SIZES[DEFAULT_SIZE].height_mm
DARK_PAGE = "#15171C"


def screen_edition(book: BookProject, size: str = DEFAULT_SIZE) -> BookProject:
    """Shallow copy of `book` (sections and assets shared, read-only) with screen settings."""
    sz = SIZES.get(size, SIZES[DEFAULT_SIZE])
    ed = copy.copy(book)
    st = copy.deepcopy(book.settings)
    st.page_size, st.width_mm, st.height_mm, st.landscape = "Custom", sz.width_mm, sz.height_mm, False
    st.margins = copy.copy(sz.margins)
    st.matter_margins = {}
    st.facing_pages = False
    st.mirrored_margins = False
    st.gutter_mm = 0.0
    st.page_multiple = 0
    st.chapter_right_page = False
    st.hyphenate = True  # narrow columns look gappy without it
    st.body_size = max(st.body_size, sz.body_pt)
    st.line_height = max(st.line_height, 1.4)
    st.footer_position = "center" if st.footer_position != "none" else "none"
    st.export_profile = "digital"
    ed.settings = st
    return ed


def _hex(c: str) -> tuple[float, float, float] | None:
    if not isinstance(c, str) or not c.startswith("#"):
        return None
    h = c[1:]
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def night_colour(c: str | None) -> str | None:
    """Flip lightness (dark ink -> light ink, light paper tint -> dark) and keep the hue."""
    rgb = _hex(c) if c else None
    if rgb is None:
        return c
    h, l, s = colorsys.rgb_to_hls(*rgb)
    r, g, b = colorsys.hls_to_rgb(h, 0.92 - 0.82 * l, s * 0.9)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _night_item(it):
    if isinstance(it, Glyphs):
        return replace(it, color=night_colour(it.color))
    if isinstance(it, LineItem):
        return replace(it, color=night_colour(it.color))
    if isinstance(it, RectItem):
        return replace(it, fill=night_colour(it.fill), stroke=night_colour(it.stroke),
                       gradient_to=night_colour(it.gradient_to))
    return it  # images keep their own colours


def night_layout(layout: LayoutResult) -> LayoutResult:
    """Dark-page copy of a laid-out book; covers (full-bleed pages) keep their design."""
    pages = []
    for p in layout.pages:
        if p.full_bleed:
            pages.append(p)
            continue
        bg = RectItem(0, 0, p.width, p.height, fill=DARK_PAGE, kind="page_background")
        pages.append(replace(p, items=[bg] + [_night_item(i) for i in p.items],
                             decorations=[_night_item(i) for i in p.decorations]))
    return replace(layout, pages=pages)
