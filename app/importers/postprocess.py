"""Shared import post-processing: poetry detection, chapter promotion, format normalisation.

Importers produce paragraphs (and `Blank` markers for empty paragraphs, which carry the
author's stanza spacing). This module turns runs of verse into PoetryBlocks that keep every
line break, indentation and blank line, so poems need no manual repair after import.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter

from ..domain.content_blocks import Block, HeadingBlock, ParagraphBlock, PoetryBlock, Run
from .base import ImportReport

SENTENCE_END = re.compile(r"[.!?…”\"»)]\s*$")
SOFT = chr(31)  # marks a soft line break inside a paragraph (Markdown newline, ...)
POEM_SPLIT_BLANKS = 3  # this many empty lines in a row start a new poem
SPACES_PER_POINT = 1 / 3.0  # converts a paragraph indent in points to leading spaces

DEFAULT_CHAPTER_PATTERN = (r"^\s*(chapter|chapitre|capitolul|capitol|cap\.|part|partea|"
                           r"kapitel|capítulo)\s+([0-9]+|[ivxlcdm]+|[a-zăâîșț]+)\b.*$")


class Blank:
    """An empty paragraph in the source (only meaningful inside verse)."""

    __slots__ = ()


def looks_like_verse(lines: list[str], *, soft_breaks: bool = False, centered: bool = False) -> bool:
    """Heuristic: are these non-empty lines a poem rather than prose?"""
    raw = [l for l in lines if l.strip()]
    leads = {len(l) - len(l.lstrip()) for l in raw}
    lines = [l.strip() for l in raw]
    if len(lines) < 2:
        return False
    lengths = [len(l) for l in lines]
    avg, longest = statistics.mean(lengths), max(lengths)
    ended = sum(1 for l in lines if SENTENCE_END.search(l)) / len(lines)
    if centered and avg <= 70:
        return True
    if len(leads) >= 2 and avg <= 70 and ended < 0.8:
        return True  # varying indentation is a strong sign of verse
    if soft_breaks and avg <= 70 and longest <= 100:
        return True  # several short lines inside ONE paragraph: line breaks are deliberate
    return len(lines) >= 3 and avg <= 52 and longest <= 85 and ended < 0.5


def lines_of(p: ParagraphBlock) -> list[str]:
    out = []
    for raw in p.plain_text().replace("\r", "").replace(SOFT, "\n").split("\n"):
        text = raw.expandtabs(4)
        indent = len(text) - len(text.lstrip())
        if p.left_indent or p.first_indent:
            indent += max(round(((p.left_indent or 0) + max(p.first_indent or 0, 0)) * SPACES_PER_POINT), 0)
        out.append(" " * min(indent, 24) + text.strip() if text.strip() else "")
    return out


class _Stanza:
    """Consecutive paragraphs with no blank line between them."""

    def __init__(self, blanks_before: int):
        self.blanks_before = blanks_before
        self.paras: list[ParagraphBlock] = []
        self.verse = False

    def lines(self) -> list[str]:
        return [l for p in self.paras for l in lines_of(p)]

    def soft(self, deliberate: bool) -> bool:
        return deliberate and any(len(lines_of(p)) > 1 for p in self.paras)

    def centered(self) -> bool:
        return all(p.align == "center" for p in self.paras)


def _stanzas(run: list) -> list[_Stanza]:
    out: list[_Stanza] = []
    blanks = 0
    for item in run:
        if isinstance(item, Blank):
            blanks += 1
            continue
        if blanks or not out:
            out.append(_Stanza(blanks))
        out[-1].paras.append(item)
        blanks = 0
    return out


def _is_title(p: ParagraphBlock, lines_after: int) -> bool:
    text = p.plain_text().strip()
    if not text or SOFT in text or "\n" in text or len(text) > 60 or lines_after < 2:
        return False
    bold = bool(p.runs) and all(r.bold for r in p.runs if r.text.strip())
    upper = text.isupper() and len(text) > 2
    return bold or p.align == "center" or upper or (not SENTENCE_END.search(text) and len(text) <= 40)


def _classify(stanzas: list[_Stanza], mode: str, deliberate: bool) -> None:
    for s in stanzas:
        s.verse = mode == "always" or looks_like_verse(
            s.lines(), soft_breaks=s.soft(deliberate), centered=s.centered())
    if mode == "always":
        return
    # Short stanzas (couplets, a lone line) next to real verse belong to the poem.
    # Several short stanzas in a row (each too small to judge alone) form a poem together.
    def short(s: _Stanza) -> bool:
        ls = [l.strip() for l in s.lines() if l.strip()]
        return bool(ls) and statistics.mean(len(l) for l in ls) <= 52 and max(len(l) for l in ls) <= 85

    i = 0
    while i < len(stanzas):
        if not short(stanzas[i]):
            i += 1
            continue
        j = i + 1
        while j < len(stanzas) and short(stanzas[j]) and stanzas[j].blanks_before < POEM_SPLIT_BLANKS:
            j += 1
        seq = [l.strip() for s in stanzas[i:j] for l in s.lines() if l.strip()]
        if len(seq) >= 4 and sum(1 for l in seq if SENTENCE_END.search(l)) / len(seq) < 0.5:
            for s in stanzas[i:j]:
                s.verse = True
        i = j
    changed = True
    while changed:  # spreads outwards from confident verse until nothing more joins
        changed = False
        for i, s in enumerate(stanzas):
            if s.verse:
                continue
            lines = [l.strip() for l in s.lines() if l.strip()]
            if not lines or len(lines) > 4 or statistics.mean(len(l) for l in lines) > 60:
                continue
            near = (i > 0 and stanzas[i - 1].verse and s.blanks_before < POEM_SPLIT_BLANKS) or \
                   (i + 1 < len(stanzas) and stanzas[i + 1].verse and
                    stanzas[i + 1].blanks_before < POEM_SPLIT_BLANKS)
            if near and not any(SENTENCE_END.search(l) and len(l) > 45 for l in lines):
                s.verse = True
                changed = True


def _build_poem(group: list[_Stanza]) -> PoetryBlock:
    title = ""
    first = group[0]
    total_lines = sum(1 for s in group for l in s.lines() if l.strip())
    if len(first.paras) == 1 and len(group) > 1 and _is_title(first.paras[0], total_lines - 1):
        title = first.paras[0].plain_text().strip()
        group = group[1:]
    lines: list[str] = []
    for idx, s in enumerate(group):
        if idx:
            lines.extend([""] * max(s.blanks_before, 1))  # every blank line the author left counts
        lines.extend(s.lines())
    poem = PoetryBlock(text="\n".join(l.rstrip() for l in lines).strip("\n"), title=title)
    if all(p.align == "center" for s in group for p in s.paras):
        poem.align = "center"
    return poem


def convert_poetry(blocks: list, mode: str, report: ImportReport, deliberate_breaks: bool = True) -> list:
    """mode: auto | always | never. Returns blocks with verse turned into PoetryBlocks."""
    if mode == "never":
        return [b for b in blocks if not isinstance(b, Blank)]
    out: list = []
    found = 0
    i = 0
    while i < len(blocks):
        if not isinstance(blocks[i], (ParagraphBlock, Blank)):
            out.append(blocks[i])
            i += 1
            continue
        j = i
        while j < len(blocks) and isinstance(blocks[j], (ParagraphBlock, Blank)):
            j += 1
        stanzas = _stanzas(blocks[i:j])
        _classify(stanzas, mode, deliberate_breaks)
        k = 0
        while k < len(stanzas):
            if not stanzas[k].verse:
                out.extend(stanzas[k].paras)
                k += 1
                continue
            group = [stanzas[k]]
            k += 1
            while k < len(stanzas) and stanzas[k].verse and stanzas[k].blanks_before < POEM_SPLIT_BLANKS:
                group.append(stanzas[k])
                k += 1
            if any(l.strip() for s in group for l in s.lines()):
                out.append(_build_poem(group))
                found += 1
        i = j
    if found:
        report.add("info", f"{found} poem(s) recognised: line breaks, indentation and blank lines "
                           f"between stanzas were kept (poetry detection: {mode})")
        report.count("poems", found)
    return out


def merge_adjacent_poems(blocks: list[Block]) -> list[Block]:
    """Consecutive PoetryBlocks (stanzas imported one by one) become one poem."""
    out: list[Block] = []
    for b in blocks:
        if isinstance(b, PoetryBlock) and out and isinstance(out[-1], PoetryBlock) and not b.title:
            out[-1].text += "\n\n" + b.text
        else:
            out.append(b)
    return out


def normalise_paragraph_format(blocks: list[Block]) -> None:
    """Drop formatting that is just the document's body default; keep only real deviations.

    Word documents carry the same indent/spacing on nearly every paragraph. Keeping that would
    override the template's typography for the whole book, so values equal to the most common
    ones are cleared; centred/right-aligned text, quotes with extra indent, etc. are kept.
    """
    paras = [b for b in blocks if isinstance(b, ParagraphBlock) and b.runs]
    if not paras:
        return
    for attr in ("left_indent", "first_indent", "space_before", "space_after"):
        vals = [round(getattr(p, attr) or 0.0, 1) for p in paras]
        mode_val, count = Counter(vals).most_common(1)[0]
        for p in paras:
            v = getattr(p, attr)
            if v is None:
                continue
            if (round(v, 1) == mode_val and count >= max(len(paras) * 0.5, 2)) or abs(v) < 0.5:
                setattr(p, attr, None)
    for p in paras:
        if p.align in ("left", "justify"):
            p.align = ""  # the template decides ordinary body alignment


def promote_chapter_headings(blocks: list[Block], level: int, pattern: str | None,
                             report: ImportReport) -> list[Block]:
    """If the document has no headings at the split level, treat 'Chapter N' lines as chapters."""
    if level <= 0 or any(isinstance(b, HeadingBlock) and b.level == level for b in blocks):
        return blocks
    try:
        rx = re.compile(pattern or DEFAULT_CHAPTER_PATTERN, re.IGNORECASE)
    except re.error:
        return blocks
    out: list[Block] = []
    n = 0
    for b in blocks:
        if isinstance(b, ParagraphBlock):
            t = b.plain_text().strip()
            if t and len(t) <= 90 and "\n" not in t and rx.match(t):
                out.append(HeadingBlock(level=level, runs=[Run(t)]))
                n += 1
                continue
        out.append(b)
    if n:
        report.add("info", f"{n} chapter title(s) recognised from text ('Chapter N' style lines) "
                           "because the document has no Heading styles")
    return out


def finish_text_blocks(blocks: list[Block], mode: str, report: ImportReport,
                       deliberate_breaks: bool) -> list[Block]:
    """Poetry detection for formats whose paragraphs have no explicit blank markers."""
    items: list = []
    for b in blocks:
        if isinstance(b, ParagraphBlock) and items and isinstance(items[-1], ParagraphBlock):
            items.append(Blank())  # paragraphs are separated by a blank line in the source
        items.append(b)
    out = convert_poetry(items, mode, report, deliberate_breaks)
    for b in out:
        if isinstance(b, ParagraphBlock):
            for r in b.runs:
                r.text = r.text.replace(SOFT, " ")
    return out
