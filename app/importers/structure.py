"""Recognising structure in exported collections (e.g. social-media post archives).

A typical export repeats: a bold header line (number + date), the poem as one paragraph with
line breaks, a right-aligned signature/hashtag, and a centred separator. These helpers classify
those paragraphs so that every post becomes its own poem instead of one endless block.
"""
from __future__ import annotations

import re

from ..domain.content_blocks import Block, ParagraphBlock, PoetryBlock, Run, runs_text
from .base import ImportReport

POST_HEADER = re.compile(r"^\s*(\d{1,5})[.)]\s+.*\b(19|20)\d{2}\b")


def _single_line(p: ParagraphBlock) -> bool:
    t = p.plain_text().strip()
    return bool(t) and "\n" not in t and chr(31) not in t


def role_of(p: ParagraphBlock) -> str:
    """title | tail | ornament | body"""
    t = p.plain_text().strip()
    if not _single_line(p):
        return "body"
    if not any(ch.isalnum() for ch in t) and len(t) <= 12:
        return "ornament"  # ---, ***, a lone dash, bullets ...
    runs = [r for r in p.runs if r.text.strip()]
    if runs and all(r.bold for r in runs) and len(t) <= 100 and p.align != "right":
        return "title"
    if p.align == "right" and len(t) <= 80:
        return "tail"  # signature, hashtag, date line
    return "body"


def is_post_header(text: str) -> bool:
    return bool(POST_HEADER.match(text or ""))


def apply_header_policy(blocks: list[Block], policy: str, report: ImportReport) -> None:
    """Numbered date headers ("12. Sep 29, 2026 8:54 am") on most poems: keep, shorten or remove."""
    poems = [b for b in blocks if isinstance(b, PoetryBlock) and b.title]
    headers = [b for b in poems if is_post_header(b.title)]
    if len(headers) < 3 or len(headers) < len(poems) * 0.5 or policy == "keep":
        if len(headers) >= 3 and policy == "keep":
            report.add("info", f"{len(headers)} poems have numbered date headers; they were kept as poem titles "
                               "(import option 'Post headers' can shorten or remove them)")
        return
    for b in headers:
        if policy == "number":
            b.title = POST_HEADER.match(b.title).group(1)
        else:
            b.title = ""
    report.add("info", f"{len(headers)} numbered date headers were "
                       + ("shortened to the poem number" if policy == "number" else "removed from the poems"))


def extract_title_block(blocks: list[Block], report: ImportReport) -> tuple[str | None, str | None, str | None, list[Block]]:
    """Leading centred lines (title, subtitle, note) become book metadata instead of body text."""
    lead: list[ParagraphBlock] = []
    for b in blocks:
        if isinstance(b, ParagraphBlock) and b.align == "center" and _single_line(b) and len(b.plain_text()) <= 140:
            lead.append(b)
            continue
        if isinstance(b, ParagraphBlock) and not b.plain_text().strip():
            continue
        break
    if not lead or len(lead) > 4:
        return None, None, None, blocks
    texts = [p.plain_text().strip() for p in lead]
    title = texts[0]
    subtitle = texts[1] if len(texts) > 1 else None
    note = " ".join(texts[2:]) or None
    rest = [b for b in blocks if not any(b is p for p in lead)]
    report.add("info", f"The centred opening lines were used as the book's title page text: '{title}'"
                       + (f", subtitle '{subtitle}'" if subtitle else "")
                       + (f", note '{note}' (stored in the book description)" if note else ""))
    return title, subtitle, note, rest
