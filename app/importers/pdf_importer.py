"""PDF import as reference material: extractable text only, scans are reported."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from ..domain.content_blocks import ParagraphBlock, Run
from ..domain.sections import Section
from .base import (ImageSink, ImportFailure, ImportOptions, ImportReport, ImportResult,
                   stem_title)

MIN_TEXT_CHARS = 20


def import_pdf(path: Path, raw: bytes, options: ImportOptions, sink: ImageSink) -> ImportResult:
    report = ImportReport(source=Path(path).name, format="PDF")
    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception as e:
        raise ImportFailure(f"The PDF could not be opened: {e}") from e
    if doc.needs_pass:
        raise ImportFailure("The PDF is password protected")
    section = Section(f"{stem_title(path)} (imported from PDF)", "chapter")
    scanned: list[int] = []
    text_pages = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        blocks = [b for b in page.get_text("blocks") if b[6] == 0]
        text = " ".join(b[4] for b in blocks)
        if len(text.strip()) < MIN_TEXT_CHARS:
            if page.get_images() or not text.strip():
                scanned.append(pno + 1)
                section.blocks.append(ParagraphBlock(
                    runs=[Run(f"[Page {pno + 1} of the PDF has no extractable text "
                              f"(scanned image); OCR is not implemented]", italic=True)]))
            continue
        text_pages += 1
        for b in blocks:
            para = re.sub(r"\s+", " ", b[4].replace("-\n", "")).strip()
            if para:
                section.blocks.append(ParagraphBlock(runs=[Run(para)]))
    if scanned:
        shown = ", ".join(map(str, scanned[:20])) + (" ..." if len(scanned) > 20 else "")
        report.add("warning", f"{len(scanned)} page(s) look scanned and were not converted to text: {shown}")
    if text_pages:
        report.add("info", "Text was extracted block by block; columns, hyphenation and "
                           "reading order may need manual review")
    report.add("info", "Images, vector graphics and page layout of the PDF were not imported")
    report.count("pages with text", text_pages)
    report.count("scanned pages", len(scanned))
    title = (doc.metadata or {}).get("title") or None
    return ImportResult([section], report, title)
