"""Page geometry of one stretch of pages: size, margins and columns.

The book's settings give the defaults. A section may override the page size, the margins and the
number of columns (`Section.page`); its sub-sections inherit the override unless they set their own.
Invalid values are ignored, never an error, so a damaged project still lays out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .layouts import MM_TO_PT, PAGE_SIZES, BookSettings

MAX_COLUMNS = 4
MIN_PAGE_MM, MAX_PAGE_MM = 40.0, 1000.0


@dataclass(frozen=True)
class PageSetup:
    width: float                                        # points
    height: float
    margins: tuple[float, float, float, float]          # top, bottom, inner, outer (points, gutter included)
    columns: int = 1
    gap: float = 0.0                                    # between columns, points

    @property
    def content_width(self) -> float:
        return max(self.width - self.margins[2] - self.margins[3], 36.0)

    @property
    def content_height(self) -> float:
        return max(self.height - self.margins[0] - self.margins[1], 36.0)

    @property
    def column_width(self) -> float:
        n = max(self.columns, 1)
        return max((self.content_width - self.gap * (n - 1)) / n, 24.0)

    def geometry(self) -> tuple:
        """What must match for two sections to share a page (columns may change within a page)."""
        return (round(self.width, 2), round(self.height, 2), tuple(round(m, 2) for m in self.margins))


def _num(v: Any, lo: float, hi: float) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if lo <= f <= hi else None


def merge_page_dicts(parent: dict | None, own: dict | None) -> dict:
    """Section override on top of the parent's override (margins merge key by key)."""
    out = dict(parent or {})
    for k, v in (own or {}).items():
        if k == "margins" and isinstance(v, dict):
            out["margins"] = {**(out.get("margins") or {}), **v}
        else:
            out[k] = v
    return out


def setup_for(settings: BookSettings, matter: str, page: dict | None = None) -> PageSetup:
    """Effective geometry for `matter` with the section override `page` applied."""
    page = page or {}
    w, h = settings.page_size_pt()
    name = page.get("page_size")
    if name in PAGE_SIZES and name != "Custom":
        wmm, hmm = PAGE_SIZES[name]
        w, h = wmm * MM_TO_PT, hmm * MM_TO_PT
    else:
        wmm, hmm = _num(page.get("width_mm"), MIN_PAGE_MM, MAX_PAGE_MM), _num(page.get("height_mm"), MIN_PAGE_MM, MAX_PAGE_MM)
        if wmm and hmm:
            w, h = wmm * MM_TO_PT, hmm * MM_TO_PT
    if page.get("landscape") and h > w:
        w, h = h, w
    m = settings.margins_for(matter)
    base = {"top": m.top, "bottom": m.bottom, "inner": m.inner + settings.gutter_mm, "outer": m.outer}
    vals = dict(base)
    for k, v in (page.get("margins") or {}).items():
        f = _num(v, 0.0, MAX_PAGE_MM / 2)
        if k in vals and f is not None:
            vals[k] = f + (settings.gutter_mm if k == "inner" else 0.0)
    margins = tuple(vals[k] * MM_TO_PT for k in ("top", "bottom", "inner", "outer"))
    cols = page.get("columns", 1)
    try:
        cols = min(max(int(cols), 1), MAX_COLUMNS)
    except (TypeError, ValueError):
        cols = 1
    gap = (_num(page.get("column_gap_mm"), 1.0, 40.0) or 8.0) * MM_TO_PT if cols > 1 else 0.0
    setup = PageSetup(w, h, margins, cols, gap)
    if setup.content_width <= 36.0 or setup.content_height <= 36.0:  # margins that leave no room: ignore them
        return PageSetup(w, h, tuple(base[k] * MM_TO_PT for k in ("top", "bottom", "inner", "outer")), cols, gap)
    return setup
