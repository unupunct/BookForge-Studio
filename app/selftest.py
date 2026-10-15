"""Headless end-to-end check used to verify an installed or packaged build.

Usage: BookForgeStudio.exe --selftest <output-folder>
Creates a small book, saves and reopens it, exports a PDF and inspects the result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pymupdf

from .domain.content_blocks import ParagraphBlock, PoetryBlock, Run
from .domain.sections import Section
from .persistence.project_archive import load_project, save_project
from .services.export_service import export_pdf
from .services.project_service import NewBookSpec, create_project
from .services.template_service import TemplateService

SAMPLE = "Ștefan își ține ceaiul în căni țesute. Școala începe în Șoimuș. ĂÂÎȘȚ ăâîșț „…”"


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
        doc = pymupdf.open(str(pdf))
        text = "\n".join(p.get_text() for p in doc)
        report.update(pages=doc.page_count, bytes=pdf.stat().st_size, fonts_embedded=res.preflight["all_fonts_embedded"],
                      romanian_ok="ĂÂÎȘȚ ăâîșț" in text, poem_ok="Line one" in text)
        report["ok"] = bool(report["romanian_ok"] and report["poem_ok"] and report["fonts_embedded"]
                            and doc.page_count >= 4 and report["templates"] >= 13)
    except Exception as e:  # report every failure instead of crashing silently
        report["error"] = f"{type(e).__name__}: {e}"
    (out / "selftest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.stdout is not None:  # windowed builds have no console
        sys.stdout.write(json.dumps(report, ensure_ascii=True) + "\n")
    return 0 if report["ok"] else 1
