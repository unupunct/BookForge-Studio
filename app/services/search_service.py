"""Book-wide search and replace on the structured model (no UI dependency)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                     ImageBlock, ListBlock, ParagraphBlock, PoetryBlock,
                                     QuoteBlock, Run, TableBlock, merge_runs, runs_text)
from ..domain.sections import Section


@dataclass
class SearchOptions:
    case_sensitive: bool = False
    whole_word: bool = False
    current_section_id: str | None = None  # None = whole book
    headings: bool = True
    code: bool = True
    captions: bool = True
    tables: bool = True
    include_hidden: bool = False
    regex: bool = False  # query is a regular expression; replacement may use \\1 group references


@dataclass
class SearchHit:
    section_id: str
    section_title: str
    block_id: str
    block_type: str
    field: str
    start: int
    end: int
    snippet: str
    locked: bool = False
    matched: str = ""


@dataclass
class ReplaceResult:
    replaced: int = 0
    skipped_locked: int = 0
    sections_changed: set[str] = field(default_factory=set)


def _replacement(replacement: str, opts: SearchOptions):
    """Literal text, or (regex mode) a callable expanding \\1 / \\g<name> group references."""
    if not opts.regex:
        return replacement

    def fn(m: re.Match) -> str:
        try:
            return m.expand(replacement)
        except (re.error, IndexError) as e:
            raise ValueError(f"Invalid replacement: {e}") from e
    return fn


def compile_pattern(query: str, opts: SearchOptions) -> re.Pattern[str]:
    body = query if opts.regex else re.escape(query)
    if opts.whole_word:
        body = rf"(?<!\w){body}(?!\w)"
    flags = re.UNICODE | (re.MULTILINE if opts.regex else 0) | (0 if opts.case_sensitive else re.IGNORECASE)
    try:
        pat = re.compile(body, flags)
    except re.error as e:
        raise ValueError(f"Invalid regular expression: {e}") from e
    if pat.match("") and opts.regex and query:
        raise ValueError("The expression matches an empty string, which would match everywhere")
    return pat


def _fields(block: Block, opts: SearchOptions):
    """Yield (field name, text) pairs permitted by the options."""
    if isinstance(block, HeadingBlock):
        if opts.headings:
            yield "runs", runs_text(block.runs)
    elif isinstance(block, (ParagraphBlock, QuoteBlock, ExerciseBlock, FootnoteBlock)):
        yield "runs", runs_text(block.runs)
        if isinstance(block, QuoteBlock) and block.attribution:
            yield "attribution", runs_text(block.attribution)
        if isinstance(block, ExerciseBlock) and block.title:
            yield "title", block.title
    elif isinstance(block, ListBlock):
        for i, it in enumerate(block.items):
            yield f"items[{i}]", runs_text(it)
    elif isinstance(block, CodeBlock):
        if opts.code:
            yield "text", block.text
        if opts.captions and block.caption:
            yield "caption", runs_text(block.caption)
    elif isinstance(block, PoetryBlock):
        yield "text", block.text
        if block.title:
            yield "title", block.title
    elif isinstance(block, TableBlock):
        if opts.tables:
            for r, row in enumerate(block.rows):
                for c, t in enumerate(row):
                    yield f"cell[{r}][{c}]", t
        if opts.captions and block.caption:
            yield "caption", runs_text(block.caption)
    elif isinstance(block, ImageBlock):
        if opts.captions and block.caption:
            yield "caption", runs_text(block.caption)


def _sections(book: BookProject, opts: SearchOptions):
    for s in book.walk():
        if opts.current_section_id and s.id != opts.current_section_id:
            continue
        if not s.enabled and not opts.include_hidden:
            continue
        yield s


def search_book(book: BookProject, query: str, opts: SearchOptions | None = None,
                limit: int = 5000) -> list[SearchHit]:
    opts = opts or SearchOptions()
    if not query:
        return []
    pat = compile_pattern(query, opts)
    hits: list[SearchHit] = []
    for s in _sections(book, opts):
        for b in s.blocks:
            for fld, text in _fields(b, opts):
                for m in pat.finditer(text):
                    a = max(m.start() - 30, 0)
                    z = min(m.end() + 30, len(text))
                    hits.append(SearchHit(s.id, s.title or s.kind, b.id, b.type, fld, m.start(),
                                          m.end(), ("…" if a else "") + text[a:z].replace("\n", " ")
                                          + ("…" if z < len(text) else ""), b.locked, m.group(0)))
                    if len(hits) >= limit:
                        return hits
    return hits


def _rep(m: re.Match, repl) -> str:
    return repl(m) if callable(repl) else repl


def _replace_runs(runs: list[Run], pat: re.Pattern[str], repl,
                  only_start: int | None = None) -> tuple[list[Run], int]:
    """Replace matches in formatted text. The replacement takes the formatting of the first
    matched character, so matches that cross formatting boundaries are handled too."""
    text = "".join(r.text for r in runs)
    fmts = [r.fmt() for r in runs for _ in r.text]
    out_text: list[str] = []
    out_fmts: list = []
    pos = 0
    n = 0
    for m in pat.finditer(text):
        if only_start is not None and m.start() != only_start:
            continue
        rep = _rep(m, repl)
        out_text.append(text[pos:m.start()])
        out_fmts.extend(fmts[pos:m.start()])
        out_text.append(rep)
        out_fmts.extend([fmts[m.start()] if m.start() < len(fmts) else Run('').fmt()] * len(rep))
        pos = m.end()
        n += 1
    out_text.append(text[pos:])
    out_fmts.extend(fmts[pos:])
    new = "".join(out_text)
    res: list[Run] = []
    for ch, f in zip(new, out_fmts):
        if res and res[-1].fmt() == f:
            res[-1].text += ch
        else:
            res.append(Run(ch, *f))
    return res, n


def _replace_str(text: str, pat: re.Pattern[str], repl,
                 only_start: int | None = None) -> tuple[str, int]:
    if only_start is None:
        return pat.subn(lambda m: _rep(m, repl), text)
    for m in pat.finditer(text):
        if m.start() == only_start:
            return text[:m.start()] + _rep(m, repl) + text[m.end():], 1
    return text, 0


def _apply(block: Block, fld: str, pat: re.Pattern[str], repl,
           only_start: int | None = None) -> int:
    """Replace inside one field of a block. Returns the number of replacements."""
    if fld == "runs" and hasattr(block, "runs"):
        block.runs, k = _replace_runs(block.runs, pat, repl, only_start)
    elif fld == "attribution" and isinstance(block, QuoteBlock):
        block.attribution, k = _replace_runs(block.attribution, pat, repl, only_start)
    elif fld == "caption" and hasattr(block, "caption"):
        block.caption, k = _replace_runs(block.caption, pat, repl, only_start)
    elif fld.startswith("items[") and isinstance(block, ListBlock):
        i = int(fld[6:-1])
        block.items[i], k = _replace_runs(block.items[i], pat, repl, only_start)
    elif fld == "title" and hasattr(block, "title"):
        block.title, k = _replace_str(block.title, pat, repl, only_start)
    elif fld == "text" and hasattr(block, "text"):
        block.text, k = _replace_str(block.text, pat, repl, only_start)
    elif fld.startswith("cell[") and isinstance(block, TableBlock):
        r, c = (int(x) for x in re.findall(r"\d+", fld))
        block.rows[r][c], k = _replace_str(block.rows[r][c], pat, repl, only_start)
    else:
        k = 0
    return k


def replace_in_book(book: BookProject, query: str, replacement: str,
                    opts: SearchOptions | None = None) -> ReplaceResult:
    """Replace every match. Locked blocks are never modified (they are counted as skipped)."""
    opts = opts or SearchOptions()
    res = ReplaceResult()
    if not query:
        return res
    pat = compile_pattern(query, opts)
    repl = _replacement(replacement, opts)
    for s in _sections(book, opts):
        for b in s.blocks:
            fields_hit = [(f, t) for f, t in _fields(b, opts) if pat.search(t)]
            if not fields_hit:
                continue
            if b.locked:
                res.skipped_locked += sum(len(pat.findall(t)) for _, t in fields_hit)
                continue
            for fld, _ in fields_hit:
                k = _apply(b, fld, pat, repl)
                if k:
                    res.replaced += k
                    res.sections_changed.add(s.id)
    return res


def replace_one(book: BookProject, hit: SearchHit, query: str, replacement: str,
                opts: SearchOptions | None = None) -> bool:
    """Replace the single occurrence described by `hit` (False if locked or stale)."""
    opts = opts or SearchOptions()
    found = book.find_block(hit.block_id)
    if found is None:
        return False
    section, block = found
    if block.locked:
        return False
    pat = compile_pattern(query, opts)
    return _apply(block, hit.field, pat, _replacement(replacement, opts), hit.start) > 0
