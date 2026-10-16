"""Export every chosen format in one go; one failure never stops the others."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..domain.book import BookProject
from ..layout.pagination import LayoutEngine
from .cover_service import CoverExportError, export_cover_pdf, spine_width_mm
from .export_service import ExportError, ValidationBlocked, export_other, export_pdf

FORMATS: list[tuple[str, str, str]] = [  # key, label, file name pattern ({b} = base name)
    ("pdf_digital", "Digital PDF", "{b}.pdf"),
    ("pdf_print", "Print PDF (bleed, crop marks)", "{b} (print).pdf"),
    ("pdf_screen", "Screen PDF - phone", "{b} (screen).pdf"),
    ("pdf_screen_tablet", "Screen PDF - tablet", "{b} (tablet).pdf"),
    ("pdf_screen_computer", "Screen PDF - computer (A4 page)", "{b} (computer).pdf"),
    ("pdf_screen_dark", "Screen PDF - phone, dark pages", "{b} (screen dark).pdf"),
    ("epub", "EPUB 3 e-book", "{b}.epub"),
    ("docx", "Word manuscript", "{b}.docx"),
    ("html", "HTML", "{b}.html"),
    ("markdown", "Markdown", "{b}.md"),
    ("cover_print", "Print cover artwork (front+back, bleed)", "{b} (cover).pdf"),
]
DEFAULT_KEYS = ["pdf_digital", "pdf_print", "pdf_screen", "epub", "docx"]
# screen PDFs: key -> (screen size, dark pages); each is laid out again for its own page format
SCREEN_VARIANTS = {"pdf_screen": ("phone", False), "pdf_screen_tablet": ("tablet", False),
                   "pdf_screen_computer": ("computer", False), "pdf_screen_dark": ("phone", True)}


@dataclass
class ExportAllItem:
    key: str
    label: str
    path: Path | None
    ok: bool
    message: str
    pages: int = 0


def safe_name(title: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(".")
    return s or "book"


def export_all(book: BookProject, folder: Path, base: str | None = None, keys: list[str] | None = None, *,
               overwrite: bool = False, allow_errors: bool = False,
               progress: Callable[[int, int, str], None] | None = None,
               cancel: Callable[[], bool] | None = None) -> list[ExportAllItem]:
    folder = Path(folder)
    if not folder.exists():
        raise ExportError(f"The folder '{folder}' does not exist")
    base = safe_name(base or book.metadata.title)
    keys = keys or DEFAULT_KEYS
    chosen = [f for f in FORMATS if f[0] in keys]
    layout = None
    if any(k in ("pdf_digital", "pdf_print", "pdf_proof", "cover_print") for k, _, _ in chosen):
        layout = LayoutEngine().build(book, cancel)
    results: list[ExportAllItem] = []
    for n, (key, label, pattern) in enumerate(chosen):
        if cancel and cancel():
            results.append(ExportAllItem(key, label, None, False, "Cancelled"))
            continue
        if progress:
            progress(n, len(chosen), label)
        dest = folder / pattern.format(b=base)
        try:
            if key in SCREEN_VARIANTS:
                size, dark = SCREEN_VARIANTS[key]
                r = export_pdf(book, dest, "screen", overwrite=overwrite, allow_errors=allow_errors, cancel=cancel,
                               screen_size=size, screen_dark=dark)
                results.append(ExportAllItem(key, label, dest, True, r.summary(), r.pages))
            elif key.startswith("pdf"):
                r = export_pdf(book, dest, key[4:], overwrite=overwrite, allow_errors=allow_errors, layout=layout,
                               cancel=cancel)
                results.append(ExportAllItem(key, label, dest, True, r.summary(), r.pages))
            elif key == "cover_print":
                interior = sum(1 for p in layout.pages if not p.full_bleed) if layout else 0
                export_cover_pdf(book, dest, "front_back", "print",
                                 spine_width_mm(interior, book.settings.paper_thickness_mm), overwrite=overwrite)
                results.append(ExportAllItem(key, label, dest, True, f"{label} written to {dest}"))
            else:
                r = export_other(book, dest, key, overwrite=overwrite)
                results.append(ExportAllItem(key, label, dest, True, r.summary()))
        except ValidationBlocked as e:
            results.append(ExportAllItem(key, label, None, False,
                                         f"Blocked by {len(e.report.errors)} validation error(s); fix them or "
                                         "export with errors allowed"))
        except (ExportError, CoverExportError, OSError) as e:
            results.append(ExportAllItem(key, label, None, False, str(e)))
        except Exception as e:  # an unexpected failure in one format must not stop the rest
            results.append(ExportAllItem(key, label, None, False, f"{type(e).__name__}: {e}"))
    if progress:
        progress(len(chosen), len(chosen), "Done")
    return results
