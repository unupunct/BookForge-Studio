"""Export workflow: validate -> temp file -> inspect -> atomic finalise."""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf

from ..domain.book import BookProject
from ..exporters.docx_exporter import export_docx
from ..exporters.epub_exporter import export_epub
from ..exporters.html_exporter import export_html
from ..exporters.markdown_exporter import export_markdown
from ..exporters.pdf_exporter import PROFILES, ExportCancelled, PdfProfile, render_pdf
from ..layout.model import ImageItem, LayoutResult
from ..layout.pagination import LayoutCancelled, LayoutEngine
from .epub_check import check_epub
from .image_service import effective_dpi
from .validation_service import ValidationReport, validate_book


class ExportError(Exception):
    """An export failed; the message is user-presentable. No partial file is left behind."""


class ValidationBlocked(ExportError):
    def __init__(self, report: ValidationReport):
        super().__init__(f"The book has {len(report.errors)} unresolved error(s)")
        self.report = report


@dataclass
class ExportResult:
    path: Path
    format: str
    pages: int = 0
    size_bytes: int = 0
    validation: ValidationReport | None = None
    preflight: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        bits = [f"{self.format} written to {self.path}"]
        if self.pages:
            bits.append(f"{self.pages} pages")
        bits.append(f"{self.size_bytes / 1024:.0f} KB")
        return ", ".join(bits)


def _temp_in(dest: Path) -> Path:
    try:
        fd, name = tempfile.mkstemp(prefix=f".{dest.stem}.", suffix=".tmp", dir=dest.parent)
    except PermissionError as e:
        raise ExportError(f"Cannot write to '{dest.parent}': permission denied") from e
    except OSError as e:
        raise ExportError(f"Cannot create a temporary file in '{dest.parent}': {e}") from e
    os.close(fd)
    return Path(name)


def inspect_pdf(path: Path, expected_pages: int, book: BookProject,
                expected_size: tuple[float, float]) -> dict:
    """Open the generated PDF and confirm it matches the layout. Raises ExportError."""
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        raise ExportError(f"The generated PDF could not be opened for verification: {e}") from e
    with doc:
        if doc.page_count != expected_pages:
            raise ExportError(f"Verification failed: PDF has {doc.page_count} pages, "
                              f"layout has {expected_pages}")
        meta = doc.metadata or {}
        if (meta.get("title") or "") != book.metadata.title:
            raise ExportError("Verification failed: PDF title metadata does not match the book")
        r = doc[0].rect
        if abs(r.width - expected_size[0]) > 0.6 or abs(r.height - expected_size[1]) > 0.6:
            raise ExportError(f"Verification failed: page size {r.width:.1f}x{r.height:.1f} pt, "
                              f"expected {expected_size[0]:.1f}x{expected_size[1]:.1f}")
        fonts = {}
        for pno in range(doc.page_count):
            for f in doc[pno].get_fonts():
                fonts[f[3]] = f[0] > 0 and f[1] != "n/a"  # xref with an embedded font file
        return {"page_count": doc.page_count, "page_size_pt": (r.width, r.height),
                "fonts": fonts, "all_fonts_embedded": all(fonts.values()) if fonts else True,
                "title": meta.get("title"), "author": meta.get("author")}


def export_pdf(book: BookProject, dest: Path, profile_key: str = "digital", *,
               overwrite: bool = False, allow_errors: bool = False,
               layout: LayoutResult | None = None, engine: LayoutEngine | None = None,
               bleed_mm: float | None = None, crop_marks: bool | None = None,
               progress: Callable[[int, int], None] | None = None,
               cancel: Callable[[], bool] | None = None,
               screen_size: str = "phone", screen_dark: bool = False) -> ExportResult:
    dest = Path(dest)
    profile: PdfProfile = PROFILES[profile_key]
    if dest.exists() and not overwrite:
        raise ExportError(f"'{dest.name}' already exists; choose another name or allow overwriting")
    if not dest.parent.exists():
        raise ExportError(f"The folder '{dest.parent}' does not exist")
    if profile_key == "screen":  # re-laid out for phones and tablets; the book itself is untouched
        from .screen_edition import night_layout, screen_edition
        book, layout = screen_edition(book, screen_size), None
    try:
        layout = layout or (engine or LayoutEngine()).build(book, cancel)
        if profile_key == "screen" and screen_dark:
            layout = night_layout(layout)
    except LayoutCancelled:
        raise ExportError("Export cancelled; no file was written") from None
    report = validate_book(book, layout, profile_key)
    if report.errors and not allow_errors:
        raise ValidationBlocked(report)
    tmp = _temp_in(dest)
    try:
        geom = render_pdf(book, layout, tmp, profile, bleed_mm, crop_marks, progress, cancel)
        info = inspect_pdf(tmp, layout.page_count, book,
                           (geom["page_width"], geom["page_height"]))
        info.update(profile=profile.key, bleed_pt=geom["bleed_pt"],
                    trim_size_pt=(geom["trim_width"], geom["trim_height"]))
        dpis = []
        for p in layout.pages:
            for it in p.items:
                if isinstance(it, ImageItem) and not it.missing:
                    a = book.assets.get(it.asset_id)
                    if a and a.data:
                        dpis.append(effective_dpi(a, it.w, it.crop))
        info["min_image_dpi"] = round(min(dpis)) if dpis else None
        info["image_count"] = len(dpis)
        try:
            os.replace(tmp, dest)
        except PermissionError as e:
            raise ExportError(f"Cannot write '{dest}': permission denied") from e
        except OSError as e:
            raise ExportError(f"Cannot finalise '{dest}': {e}") from e
    except ExportCancelled:
        tmp.unlink(missing_ok=True)
        raise ExportError("Export cancelled; no file was written") from None
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    notes = ["Not validated against PDF/X or other print standards; run a preflight in your "
             "printer's tool before ordering."] if profile_key == "print" else []
    return ExportResult(dest, f"{profile.label}", layout.page_count, dest.stat().st_size,
                        report, info, notes)


def export_other(book: BookProject, dest: Path, fmt: str, overwrite: bool = False) -> ExportResult:
    dest = Path(dest)
    if dest.exists() and not overwrite:
        raise ExportError(f"'{dest.name}' already exists; choose another name or allow overwriting")
    if not dest.parent.exists():
        raise ExportError(f"The folder '{dest.parent}' does not exist")
    tmp = _temp_in(dest)
    notes: list[str] = []
    try:
        if fmt == "docx":
            notes = export_docx(book, tmp)
        elif fmt == "epub":
            notes = export_epub(book, tmp)
            problems = check_epub(tmp)
            if problems:  # never hand over a package we know is broken
                raise ExportError("The EPUB failed its structural check: " + "; ".join(problems[:3]))
        elif fmt == "html":
            export_html(book, tmp)
        elif fmt == "markdown":
            notes = export_markdown(book, dest, write_to=tmp)
        else:
            raise ExportError(f"Unknown export format '{fmt}'")
        os.replace(tmp, dest)
    except PermissionError as e:
        raise ExportError(f"Cannot write '{dest}': permission denied") from e
    except ExportError:
        raise
    except Exception as e:
        raise ExportError(f"Export failed: {e}") from e
    finally:
        tmp.unlink(missing_ok=True)
    return ExportResult(dest, fmt.upper(), 0, dest.stat().st_size, None, {}, notes)
