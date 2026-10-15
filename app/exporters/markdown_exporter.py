"""Markdown export of the structured content. Images go to a sibling folder."""
from __future__ import annotations

import re
from pathlib import Path

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                     ImageBlock, ListBlock, PageBreakBlock, ParagraphBlock,
                                     PoetryBlock, QuoteBlock, RecipeBlock, Run, SceneBreakBlock,
                                     TableBlock, runs_text)
from ..domain.sections import GENERATED_KINDS, Section
from ..layout.page_builder import EXERCISE_LABELS

_ESC = re.compile(r"([\\`*_{}\[\]<>#|])")


def _esc(t: str) -> str:
    return _ESC.sub(r"\\\1", t)


def _runs(runs: list[Run]) -> str:
    out = []
    for r in runs:
        if r.code:
            t = f"`{r.text}`"
        else:
            t = _esc(r.text).replace("\n", "  \n")
            if r.bold and r.italic:
                t = f"***{t}***"
            elif r.bold:
                t = f"**{t}**"
            elif r.italic:
                t = f"*{t}*"
        if r.link:
            t = f"[{t}]({r.link})"
        out.append(t)
    return "".join(out)


def render_markdown(book: BookProject, image_dir_name: str,
                    images: dict[str, tuple[str, bytes]]) -> tuple[str, list[str]]:
    md = book.metadata
    notes: list[str] = []
    out: list[str] = [f"# {_esc(md.title)}"]
    if md.subtitle:
        out.append(f"*{_esc(md.subtitle)}*")
    if md.author:
        out.append(f"**{_esc(md.author)}**")

    def block(b: Block) -> str:
        if isinstance(b, ParagraphBlock):
            return _runs(b.runs)
        if isinstance(b, HeadingBlock):
            return "#" * min(b.level + 2, 6) + " " + _runs(b.runs)
        if isinstance(b, ListBlock):
            return "\n".join((f"{i + 1}. " if b.ordered else "- ") + _runs(it) for i, it in enumerate(b.items))
        if isinstance(b, QuoteBlock):
            q = "> " + _runs(b.runs)
            return q + (f"\n>\n> \u2014 {_runs(b.attribution)}" if b.attribution else "")
        if isinstance(b, CodeBlock):
            fence = "````" if "```" in b.text else "```"
            return f"{fence}{b.language}\n{b.text}\n{fence}"
        if isinstance(b, PoetryBlock):
            lines = [(_esc(l) + "  ") if l.strip() else "" for l in b.text.split("\n")]
            return (f"**{_esc(b.title)}**\n\n" if b.title else "") + "\n".join(lines)
        if isinstance(b, ImageBlock):
            a = book.assets.get(b.asset)
            if a is None or not a.data:
                notes.append("An image was missing and was left out of the Markdown")
                return f"*[Missing image: {_esc(b.alt)}]*"
            fname = images.setdefault(b.asset, (re.sub(r"[^A-Za-z0-9._-]", "_", f"{a.id}_{a.filename}"), a.data))[0]
            cap = runs_text(b.caption)
            return f"![{_esc(b.alt)}]({image_dir_name}/{fname}" + (f' "{cap}")' if cap else ")")
        if isinstance(b, TableBlock):
            if not b.rows:
                return ""
            n = max(len(r) for r in b.rows)
            rows = [[c.replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (n - len(r)) for r in b.rows]
            head = rows[0]
            lines = ["| " + " | ".join(head) + " |", "|" + "---|" * n]
            lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
            if b.caption:
                lines.append("\n*" + _runs(b.caption) + "*")
            return "\n".join(lines)
        if isinstance(b, SceneBreakBlock):
            return "* * *"
        if isinstance(b, PageBreakBlock):
            return "<!-- page break -->"
        if isinstance(b, RecipeBlock):
            p = [f"### {_esc(b.title)}"]
            meta = [f"{k}: {v}" for k, v in (("Prep", b.prep_time), ("Cook", b.cook_time),
                                              ("Serves", b.servings)) if v]
            if meta:
                p.append("*" + " · ".join(meta) + "*")
            if b.description:
                p.append(_esc(b.description))
            if b.ingredients:
                p.append("**Ingredients**\n\n" + "\n".join(f"- {_esc(i)}" for i in b.ingredients))
            if b.instructions:
                p.append("**Method**\n\n" + "\n".join(f"{n + 1}. {_esc(i)}" for n, i in enumerate(b.instructions)))
            if b.notes:
                p.append("**Notes:** " + _esc(b.notes))
            if b.nutrition:
                p.append("**Nutrition (as supplied):** " + _esc(b.nutrition))
            return "\n\n".join(p)
        if isinstance(b, ExerciseBlock):
            label = EXERCISE_LABELS.get(b.kind, b.kind.title())
            return f"> **{label}{': ' + b.title if b.title else ''}** {_runs(b.runs)}"
        if isinstance(b, FootnoteBlock):
            return f"{_esc(b.label)} {_runs(b.runs)}"
        return ""

    def rec(sections: list[Section], depth: int) -> None:
        for s in sections:
            if not s.enabled or (s.kind in GENERATED_KINDS and not s.blocks):
                continue
            if s.title and s.show_title:
                out.append("#" * min(depth + 1, 6) + " " + _esc(s.title))
            out.extend(x for x in (block(b) for b in s.blocks) if x)
            rec(s.children, depth + 1)

    rec(book.sections, 1)
    notes.append("Page layout, styles, covers and generated pages are not part of Markdown export")
    return "\n\n".join(out) + "\n", sorted(set(notes))


def export_markdown(book: BookProject, path: Path, write_to: Path | None = None) -> list[str]:
    """Write Markdown for `path` (text goes to `write_to` first when given, e.g. a temp file)."""
    path = Path(path)
    folder = path.stem + "_images"
    images: dict[str, tuple[str, bytes]] = {}
    text, notes = render_markdown(book, folder, images)
    (write_to or path).write_text(text, encoding="utf-8")
    if images:
        d = path.parent / folder
        d.mkdir(exist_ok=True)
        for name, data in images.values():
            (d / name).write_bytes(data)
    return notes
