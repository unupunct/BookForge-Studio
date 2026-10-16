"""Headless end-to-end check used to verify an installed or packaged build.

Usage: BookForgeStudio.exe --selftest <output-folder>
Creates a small book, saves and reopens it, exports a PDF and inspects the result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

from .domain.content_blocks import ImageBlock, LayoutBlock, ParagraphBlock, PoetryBlock, Run, TextBoxBlock
from .domain.sections import Section
from .persistence.project_archive import load_project, save_project
from .layout.hyphenation import get_hyphenator
from .services.epub_check import check_epub
from .services.export_service import export_other, export_pdf
from .services.project_service import NewBookSpec, create_project
from .services.template_service import TemplateService

SAMPLE = "Ștefan își ține ceaiul în căni țesute. Școala începe în Șoimuș. ĂÂÎȘȚ ăâîșț „…”"


def _check_page_layouts(out: Path) -> bool:
    """Columns, a section with its own page size, a floated image, a pinned text box, a photo page, screen PDF."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (300, 200), (40, 120, 200)).save(buf, "PNG")
    book = create_project(NewBookSpec(title="Layouts", author="BookForge", profile="novel", cover=False))
    img = book.add_asset(buf.getvalue(), "pic.png").id
    text = lambda t: ParagraphBlock(runs=[Run(t * 12)])
    cols = Section("Columns", "chapter", blocks=[text("Two column text. ") for _ in range(4)])
    cols.page = {"columns": 2}
    wrap = Section("Wrap", "chapter", blocks=[ImageBlock(asset=img, width_pct=40, place="wrap_left"), text("Wrapped words. "),
                                              TextBoxBlock(text="PINNED BOX", px=0.1, py=0.7, pw=0.4, ph=0.08)])
    photo = Section("Photo", "chapter", blocks=[LayoutBlock(layout="photo_full", asset=img, headline="PHOTO PAGE")])
    small = Section("Small", "chapter", blocks=[text("Small page. ")])
    small.page = {"width_mm": 100, "height_mm": 140}
    toc = next((i for i, s in enumerate(book.sections) if s.kind == "chapter"), len(book.sections))
    book.sections = [s for s in book.sections if s.kind != "chapter"]
    book.sections[toc:toc] = [cols, wrap, photo, small]
    pdf = out / "layouts.pdf"
    export_pdf(book, pdf, "digital", overwrite=True, allow_errors=True)
    doc = pymupdf.open(str(pdf))
    words = "\n".join(p.get_text() for p in doc)
    sizes = {(round(p.rect.width), round(p.rect.height)) for p in doc}
    export_pdf(book, out / "layouts-screen.pdf", "screen", overwrite=True, allow_errors=True, screen_dark=True)
    return bool("Two column text" in words and "Wrapped words" in words and "PINNED BOX" in words
                and "PHOTO PAGE" in words and len(sizes) >= 2)


def run(out_dir: str) -> int:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"ok": False}
    try:
        report["templates"] = len(TemplateService().list_templates())
        book = create_project(NewBookSpec(title="Self-test Școală", author="BookForge", profile="novel"))
        ch = next(s for s in book.sections if s.kind == "chapter")
        ch.blocks = [ParagraphBlock(runs=[Run(SAMPLE * 20)]),
                     PoetryBlock(title="Poem", text="Line one\nLine two\n\nStanza two")]
        project_path = out / "selftest.bookforge"
        save_project(book, project_path)
        reopened = load_project(project_path)
        pdf = out / "selftest.pdf"
        res = export_pdf(reopened, pdf, "digital", overwrite=True, allow_errors=True)
        epub = out / "selftest.epub"
        export_other(reopened, epub, "epub", overwrite=True)
        report["epub_problems"] = check_epub(epub)
        report["hyphenation"] = get_hyphenator("ro") is not None
        doc = pymupdf.open(str(pdf))
        text = "\n".join(p.get_text() for p in doc)
        report.update(pages=doc.page_count, bytes=pdf.stat().st_size, fonts_embedded=res.preflight["all_fonts_embedded"],
                      romanian_ok="ĂÂÎȘȚ ăâîșț" in text, poem_ok="Line one" in text)
        report["layouts_ok"] = _check_page_layouts(out)
        report["ok"] = bool(report["layouts_ok"] and report["romanian_ok"] and report["poem_ok"] and report["fonts_embedded"]
                            and doc.page_count >= 4 and report["templates"] >= 13
                            and not report["epub_problems"] and report["hyphenation"])
    except Exception as e:  # report every failure instead of crashing silently
        report["error"] = f"{type(e).__name__}: {e}"
    (out / "selftest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.stdout is not None:  # windowed builds have no console
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + "\n")
    return 0 if report["ok"] else 1
