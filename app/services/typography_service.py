"""Typography cleanup: typographic quotes, dashes, ellipses and spacing, applied to the whole book.

Formatting (bold, italic, links...) is preserved. Code blocks are never touched; locked blocks are
skipped. The same function counts changes (dry run) and applies them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                     ImageBlock, ListBlock, ParagraphBlock, PoetryBlock,
                                     QuoteBlock, Run, TableBlock, merge_runs)

QUOTES = {  # language style -> (open, close)
    "ro": ("„", "”"), "de": ("„", "“"), "en": ("“", "”"),
    "fr": ("« ", " »"), "plain": ("“", "”"),
}
QUOTE_STYLES = {"ro": "Romanian „”", "en": "English “”", "de": "German „“",
                "fr": "French « »"}
OPENERS = " \t\n([{—–- „“«"


@dataclass
class CleanupOptions:
    quotes: str | None = "ro"  # None leaves quotes alone
    apostrophes: bool = True  # ' between letters -> typographic apostrophe
    dashes: bool = True  # " - " and "--" -> em dash; dialogue "- " at line start -> em dash
    ellipsis: bool = True  # ... -> ellipsis character
    spaces: bool = True  # collapse double spaces, trim line ends, no space before , . ; : ! ?
    include_poetry: bool = True


@dataclass
class CleanupReport:
    counts: dict[str, int] = field(default_factory=dict)
    blocks_changed: int = 0
    skipped_locked: int = 0

    def add(self, key: str, n: int = 1) -> None:
        if n:
            self.counts[key] = self.counts.get(key, 0) + n

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def text(self) -> str:
        if not self.counts:
            return "Nothing to change."
        names = {"quotes": "quotation marks", "apostrophes": "apostrophes", "dashes": "dashes",
                 "ellipsis": "ellipses", "spaces": "spacing fixes"}
        return ", ".join(f"{n} {names.get(k, k)}" for k, n in self.counts.items())


def _clean_text(text: str, prev: str, o: CleanupOptions, rep: CleanupReport, line_start: bool) -> str:
    """Clean one run of text. `prev` is the character before it (quotes depend on it)."""
    out = text
    if o.ellipsis:
        n = out.count("...")
        if n:
            out = out.replace("...", "…")
            rep.add("ellipsis", n)
    if o.dashes:
        n = out.count("--")
        if n:
            out = out.replace("--", "—")
            rep.add("dashes", n)
        out, k = re.subn(r"(?<=\S) - (?=\S)", " — ", out)
        rep.add("dashes", k)
        if line_start:  # dialogue dash at the start of a paragraph
            out, k = re.subn(r"^-\s+", "— ", out)
            rep.add("dashes", k)
        out, k = re.subn(r"\n-\s+", "\n— ", out)  # ... and at the start of each verse line
        rep.add("dashes", k)
    if o.apostrophes:
        out, k = re.subn(r"(?<=\w)'(?=\w)", "’", out)
        rep.add("apostrophes", k)
    if o.quotes in QUOTES:
        op, cl = QUOTES[o.quotes]
        chars = []
        before = prev
        for ch in out:
            if ch == '"':
                chars.append(op if (not before or before in OPENERS) else cl)
                rep.add("quotes")
            elif ch in "“”„«»" and ch not in (op, cl) and not o.quotes == "fr":
                # normalise other styles to the chosen one
                if ch in "„“«":
                    chars.append(op)
                else:
                    chars.append(cl)
                rep.add("quotes")
            else:
                chars.append(ch)
            before = chars[-1]
        out = "".join(chars)
    if o.spaces:
        out, k = re.subn(r"(?<=\S)[ \t]{2,}(?=\S)", " ", out)
        rep.add("spaces", k)
        out, k = re.subn(r"[ \t]+(?=\n)", "", out)
        rep.add("spaces", k)
        out, k = re.subn(r"(?<=\w) +(?=[,.;:!?](?:\s|$))", "", out)
        rep.add("spaces", k)
    return out


def _clean_runs(runs: list[Run], o: CleanupOptions, rep: CleanupReport, line_start: bool = True) -> list[Run]:
    out: list[Run] = []
    prev = ""
    for i, r in enumerate(runs):
        t = _clean_text(r.text, prev, o, rep, line_start and i == 0)
        out.append(Run(t, *r.fmt()))
        prev = t[-1] if t else prev
    res = merge_runs(out)
    if o.spaces and res:
        stripped = res[-1].text.rstrip(" \t")
        if stripped != res[-1].text:
            rep.add("spaces")
            res[-1] = Run(stripped, *res[-1].fmt())
    return res


def _clean_str(s: str, o: CleanupOptions, rep: CleanupReport) -> str:
    return _clean_text(s, "", o, rep, True)


def clean_block(b: Block, o: CleanupOptions, rep: CleanupReport) -> None:
    if isinstance(b, CodeBlock) or isinstance(b, ImageBlock) and not b.caption:
        return
    if isinstance(b, (ParagraphBlock, HeadingBlock, QuoteBlock, ExerciseBlock, FootnoteBlock)):
        b.runs = _clean_runs(b.runs, o, rep)
        if isinstance(b, QuoteBlock):
            b.attribution = _clean_runs(b.attribution, o, rep)
        if isinstance(b, ExerciseBlock):
            b.title = _clean_str(b.title, o, rep)
    elif isinstance(b, ListBlock):
        b.items = [_clean_runs(it, o, rep) for it in b.items]
    elif isinstance(b, PoetryBlock) and o.include_poetry:
        b.text = _clean_str(b.text, o, rep)
        b.title = _clean_str(b.title, o, rep)
        b.signature = _clean_str(b.signature, o, rep)
    elif isinstance(b, TableBlock):
        b.rows = [[_clean_str(c, o, rep) for c in row] for row in b.rows]
    if hasattr(b, "caption") and getattr(b, "caption", None):
        b.caption = _clean_runs(b.caption, o, rep)


def cleanup_book(book: BookProject, o: CleanupOptions | None = None, *, apply: bool = True) -> CleanupReport:
    """Clean every enabled section. With apply=False the book is untouched and only counted."""
    o = o or CleanupOptions()
    rep = CleanupReport()
    work = book if apply else None
    for s in book.walk():
        if not s.enabled:
            continue
        if apply:
            s.title = _clean_str(s.title, o, rep)
        for b in s.blocks:
            if b.locked:
                rep.skipped_locked += 1
                continue
            if apply:
                before = repr(b.to_dict())
                clean_block(b, o, rep)
                if repr(b.to_dict()) != before:
                    rep.blocks_changed += 1
            else:
                probe = Block.from_dict(b.to_dict())
                clean_block(probe, o, rep)
                if probe.to_dict() != b.to_dict():
                    rep.blocks_changed += 1
    return rep
