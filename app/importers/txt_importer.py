"""Plain-text import with encoding detection, chapter delimiters and title detection."""
from __future__ import annotations

import codecs
import re
from pathlib import Path

from ..domain.content_blocks import Block, ParagraphBlock, PoetryBlock, Run, SceneBreakBlock
from .postprocess import Blank, convert_poetry
from ..domain.sections import Section
from .base import (ImageSink, ImportFailure, ImportOptions, ImportReport, ImportResult,
                   split_into_sections, stem_title)

DEFAULT_CHAPTER_PATTERN = (r"^\s*(chapter|chapitre|capitolul|capitol|cap\.|part|partea|"
                           r"kapitel|capítulo)\s+([0-9]+|[ivxlcdm]+|[a-zăâîșț]+)\b.*$")
SCENE_BREAK = re.compile(r"^\s*([*\-_~#=]\s*){3,}\s*$")


def decode_text(raw: bytes, encoding: str | None, report: ImportReport) -> str:
    if encoding:
        try:
            codecs.lookup(encoding)
        except LookupError as e:
            raise ImportFailure(f"Unknown encoding '{encoding}'") from e
        text = raw.decode(encoding, errors="replace")
        if "�" in text:
            report.add("warning", f"Some bytes were not valid {encoding}; replaced with U+FFFD "
                                  f"({text.count(chr(0xFFFD))} occurrences)")
        return text.lstrip("﻿")
    if raw.startswith(codecs.BOM_UTF8):
        report.add("info", "UTF-8 byte-order mark removed")
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        report.add("info", "Decoded as UTF-16 (byte-order mark found)")
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        report.add("warning", "File is not valid UTF-8; decoded as Windows-1252. "
                              "Choose another encoding if characters look wrong.")
        return raw.decode("cp1252", errors="replace")


def import_txt(path: Path, raw: bytes, options: ImportOptions, sink: ImageSink) -> ImportResult:
    report = ImportReport(source=Path(path).name, format="TXT")
    text = decode_text(raw, options.encoding, report).replace("\r\n", "\n").replace("\r", "\n")
    try:
        chapter_re = re.compile(options.chapter_pattern or DEFAULT_CHAPTER_PATTERN, re.IGNORECASE)
    except re.error as e:
        raise ImportFailure(f"Invalid chapter pattern: {e}") from e

    lines = text.split("\n")
    doc_title: str | None = None
    if options.detect_title:
        first = next((i for i, l in enumerate(lines) if l.strip()), None)
        if first is not None:
            cand = lines[first].strip()
            nxt_blank = first + 1 >= len(lines) or not lines[first + 1].strip()
            if len(cand) <= 100 and nxt_blank and not chapter_re.match(cand) \
                    and not SCENE_BREAK.match(cand):
                doc_title = cand
                lines = lines[:first] + lines[first + 1:]
                report.add("info", f"First line used as document title: '{cand}'")

    chapters: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in lines:
        if chapter_re.match(line) and line.strip():
            chapters.append((line.strip(), []))
        else:
            chapters[-1][1].append(line)

    sections: list[Section] = []
    fallback = doc_title or stem_title(path)
    for title, body in chapters:
        blocks = _paragraphs(body, "always" if options.preserve_line_breaks else options.poetry_mode, report)
        if title is None and not blocks:
            continue
        sections.append(Section(title or fallback, "chapter", blocks=blocks))
    if not sections:
        sections.append(Section(fallback, "chapter"))
        report.add("warning", "The file contains no text")
    report.count("chapters", len(sections))
    report.count("paragraphs", sum(len(s.blocks) for s in sections))
    return ImportResult(sections, report, doc_title)


def _paragraphs(lines: list[str], mode: str, report: ImportReport) -> list[Block]:
    """Group lines into paragraphs; verse keeps its lines, indentation and blank lines."""
    blocks: list = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            blocks.append(ParagraphBlock(runs=[Run("\n".join(l.rstrip() for l in buf))]))
            buf.clear()

    for line in lines:
        if not line.strip():
            flush()
            blocks.append(Blank())
        elif SCENE_BREAK.match(line):
            flush()
            blocks.append(SceneBreakBlock())
        else:
            buf.append(line.expandtabs(4))
    flush()
    out = convert_poetry(blocks, mode, report, deliberate_breaks=False)
    for b in out:  # hard-wrapped prose: join the physical lines of a paragraph
        if isinstance(b, ParagraphBlock):
            b.runs = [Run(" ".join(b.runs[0].text.split()))]
    return out
