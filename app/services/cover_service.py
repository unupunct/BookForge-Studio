"""Cover artwork exports: digital front cover and print cover (separate, or wrap-around)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pymupdf

from ..domain.book import BookProject
from ..domain.layouts import MM_TO_PT
from ..exporters.pdf_exporter import PROFILES, render_pdf
from ..layout.cover_builder import wrap_items
from ..layout.model import LayoutResult, Page
from ..layout.page_builder import cover_items

KINDS = ("front", "back", "front_back", "wrap")


class CoverExportError(Exception):
    pass


def spine_width_mm(interior_pages: int, leaf_thickness_mm: float) -> float:
    """Estimate only: leaves x thickness. Printers publish their own figures; confirm with them."""
    return max(interior_pages, 0) / 2.0 * max(leaf_thickness_mm, 0.0)


def build_cover_layout(book: BookProject, kind: str, spine_mm: float = 0.0,
                       bleed_mm: float = 0.0) -> LayoutResult:
    """Pages for cover artwork. Positions come from the same cover items the preview draws."""
    W, H = book.settings.page_size_pt()

    def page(items, width, idx=0):
        return Page(index=idx, width=width, height=H, side="recto", content_box=(0, 0, width, H),
                    items=items, full_bleed=True, used=True)

    front = cover_items(book, W, H, False)
    back = cover_items(book, W, H, True)
    if kind == "front":
        pages, width = [page(front, W)], W
    elif kind == "back":
        pages, width = [page(back, W)], W
    elif kind == "front_back":
        pages, width = [page(front, W, 0), page(back, W, 1)], W
    elif kind == "wrap":
        spine = max(spine_mm, 0.0) * MM_TO_PT
        width = 2 * W + spine
        pages = [page(wrap_items(book, front, back, W, H, spine, bleed_mm * MM_TO_PT), width)]
    else:
        raise CoverExportError(f"Unknown cover export '{kind}'")
    return LayoutResult(pages=pages, page_width=width, page_height=H)


def export_cover_pdf(book: BookProject, dest: Path, kind: str, profile_key: str = "print",
                     spine_mm: float = 0.0, overwrite: bool = False, crop_marks: bool | None = None) -> Path:
    """Cover artwork as PDF. 'print' adds bleed (and crop marks); 'digital' is plain trim size."""
    dest = Path(dest)
    if dest.exists() and not overwrite:
        raise CoverExportError(f"'{dest.name}' already exists")
    if not dest.parent.exists():
        raise CoverExportError(f"The folder '{dest.parent}' does not exist")
    profile = PROFILES[profile_key]
    layout = build_cover_layout(book, kind, spine_mm,
                                book.settings.bleed_mm if profile_key == "print" else 0.0)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{dest.stem}.", suffix=".tmp", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        geom = render_pdf(book, layout, tmp, profile,
                          bleed_mm=book.settings.bleed_mm if profile_key == "print" else None,
                          crop_marks=crop_marks)
        with pymupdf.open(str(tmp)) as doc:
            if doc.page_count != len(layout.pages):
                raise CoverExportError("Verification failed: wrong page count")
            r = doc[0].rect
            if abs(r.width - geom["page_width"]) > 0.6 or abs(r.height - geom["page_height"]) > 0.6:
                raise CoverExportError("Verification failed: wrong page size")
        os.replace(tmp, dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest
