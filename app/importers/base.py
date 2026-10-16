"""Shared importer types: options, results and the import report."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..domain.content_blocks import Block, HeadingBlock, ParagraphBlock, runs_text
from ..domain.sections import Section

MAX_IMPORT_BYTES = 300 * 1024 * 1024


class ImportFailure(Exception):
    """The file could not be imported at all (message is user-presentable)."""


@dataclass
class ImportOptions:
    encoding: str | None = None  # None -> auto-detect (UTF-8, BOM aware)
    split_level: int = 1  # heading level that starts a new chapter; 0 = single chapter
    chapter_pattern: str | None = None  # TXT: regex matching chapter heading lines
    detect_title: bool = True  # TXT: first short line followed by a blank line is the title
    preserve_line_breaks: bool = False  # TXT: keep line breaks (poetry) instead of joining
    update_metadata: bool = False  # set book title from the document when it is still default
    poetry_mode: str = "auto"  # auto | always | never: keep verse line by line
    keep_formatting: bool = True  # keep alignment/indent/spacing that differs from the body text
    header_lines: str = "number"  # numbered date headers on poems: keep | number | drop
    signature_lines: str = "auto"  # right-aligned lines: auto (drop only boilerplate repeated 3+ times) | keep | drop


@dataclass
class ImportIssue:
    severity: str  # info | warning | error
    message: str


@dataclass
class ImportReport:
    source: str = ""
    format: str = ""
    issues: list[ImportIssue] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def add(self, severity: str, message: str) -> None:
        # collapse exact duplicates into a counter to keep reports readable
        for i in self.issues:
            if i.severity == severity and i.message == message:
                return
        self.issues.append(ImportIssue(severity, message))

    def count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    @property
    def has_warnings(self) -> bool:
        return any(i.severity in ("warning", "error") for i in self.issues)

    def to_dict(self) -> dict:
        return {"source": self.source, "format": self.format, "stats": self.stats,
                "issues": [{"severity": i.severity, "message": i.message} for i in self.issues]}

    def text(self) -> str:
        lines = [f"Import report: {self.source} ({self.format})"]
        if self.stats:
            lines.append("Imported: " + ", ".join(f"{v} {k}" for k, v in self.stats.items()))
        if not self.issues:
            lines.append("No conversion issues.")
        for i in self.issues:
            lines.append(f"[{i.severity.upper()}] {i.message}")
        return "\n".join(lines)


@dataclass
class ImportResult:
    sections: list[Section]
    report: ImportReport
    title: str | None = None
    author: str | None = None
    subtitle: str | None = None
    description: str | None = None
    language: str | None = None  # guessed from the text (en, ro, fr, ...), None if unsure


# (data, filename) -> asset id, or None when the image is rejected
ImageSink = Callable[[bytes, str], str | None]


def split_into_sections(blocks: list[Block], level: int, fallback_title: str,
                        report: ImportReport) -> list[Section]:
    """Group blocks into chapters at headings of `level` (0 disables splitting)."""
    if level <= 0:
        return [Section(fallback_title, "chapter", blocks=blocks)]
    sections: list[Section] = []
    current: Section | None = None
    preface: list[Block] = []
    for b in blocks:
        if isinstance(b, HeadingBlock) and b.level == level:
            if current is None and preface:
                sections.append(Section(fallback_title, "chapter", blocks=preface))
                preface = []
            current = Section(runs_text(b.runs).strip() or "Untitled", "chapter")
            sections.append(current)
            continue
        if isinstance(b, HeadingBlock) and b.level > level:
            b.level = max(b.level - level, 1)
        if current is None:
            preface.append(b)
        else:
            current.blocks.append(b)
    if current is None:
        sections.append(Section(fallback_title, "chapter", blocks=preface))
    elif preface:  # unreachable, kept for clarity
        sections.insert(0, Section(fallback_title, "chapter", blocks=preface))
    if len(sections) > 1 and sections[0].title == fallback_title and not sections[0].blocks:
        sections.pop(0)
    report.count("chapters", len(sections))
    return sections


def stem_title(path: Path) -> str:
    s = re.sub(r"[_\-]+", " ", Path(path).stem).strip()
    return s[:1].upper() + s[1:] if s else "Imported text"


def make_paragraph(text: str) -> ParagraphBlock:
    from ..domain.content_blocks import Run
    return ParagraphBlock(runs=[Run(text)] if text else [])
