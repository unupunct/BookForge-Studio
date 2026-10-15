"""Single-file HTML export for digital distribution (images embedded)."""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                     ImageBlock, ListBlock, PageBreakBlock, ParagraphBlock,
                                     PoetryBlock, QuoteBlock, RecipeBlock, Run, SceneBreakBlock,
                                     TableBlock, runs_text)
from ..domain.sections import GENERATED_KINDS, Section
from ..layout.page_builder import EXERCISE_LABELS

CSS = """
body{max-width:42em;margin:2em auto;padding:0 1em;font-family:Georgia,'Times New Roman',serif;
line-height:1.6;color:#222}
h1,h2,h3,h4{font-family:'Segoe UI',Arial,sans-serif;line-height:1.25}
.chapter{margin-top:3em}.poem{white-space:pre-line;margin:1.2em 0 1.2em 2em}
pre{background:#f3f3f3;padding:.8em;overflow:auto}blockquote{font-style:italic;margin-left:2em}
figure{text-align:center}figcaption{font-size:.85em;font-style:italic}
table{border-collapse:collapse}td,th{border:1px solid #999;padding:.3em .6em}
.callout{background:#f6f1e7;border-left:4px solid #c97b3c;padding:.5em 1em}
.scene{text-align:center}nav ul{list-style:none}
"""


def _runs(runs: list[Run]) -> str:
    out = []
    for r in runs:
        t = html.escape(r.text).replace("\n", "<br>")
        if r.code:
            t = f"<code>{t}</code>"
        if r.bold:
            t = f"<strong>{t}</strong>"
        if r.italic:
            t = f"<em>{t}</em>"
        if r.underline:
            t = f"<u>{t}</u>"
        if r.link and r.link.lower().startswith(("http://", "https://", "mailto:")):
            t = f'<a href="{html.escape(r.link, quote=True)}">{t}</a>'
        out.append(t)
    return "".join(out)


def _image_tag(book: BookProject, b: ImageBlock) -> str:
    a = book.assets.get(b.asset)
    if a is None or not a.data:
        return f"<p><em>[Missing image: {html.escape(b.alt)}]</em></p>"
    mime = "image/png" if a.data[:4] == b"\x89PNG" else "image/jpeg" if a.data[:2] == b"\xff\xd8" else None
    data = a.data
    if mime is None:  # convert formats browsers may not display (e.g. WebP is fine, but TIFF is not)
        from PIL import Image
        buf = io.BytesIO()
        with Image.open(io.BytesIO(a.data)) as im:
            im.convert("RGBA").save(buf, "PNG")
        data, mime = buf.getvalue(), "image/png"
    uri = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    cap = f"<figcaption>{_runs(b.caption)}</figcaption>" if b.caption else ""
    return (f'<figure><img src="{uri}" alt="{html.escape(b.alt, quote=True)}" '
            f'style="max-width:{b.width_pct:.0f}%">{cap}</figure>')


def _block(book: BookProject, b: Block) -> str:
    if isinstance(b, ParagraphBlock):
        return f"<p>{_runs(b.runs)}</p>"
    if isinstance(b, HeadingBlock):
        lvl = min(b.level + 2, 6)
        return f'<h{lvl} id="blk-{b.id}">{_runs(b.runs)}</h{lvl}>'
    if isinstance(b, ListBlock):
        tag = "ol" if b.ordered else "ul"
        return f"<{tag}>" + "".join(f"<li>{_runs(i)}</li>" for i in b.items) + f"</{tag}>"
    if isinstance(b, QuoteBlock):
        attr = f"<footer>— {_runs(b.attribution)}</footer>" if b.attribution else ""
        return f"<blockquote><p>{_runs(b.runs)}</p>{attr}</blockquote>"
    if isinstance(b, CodeBlock):
        return f"<pre><code>{html.escape(b.text)}</code></pre>"
    if isinstance(b, PoetryBlock):
        title = f"<h4>{html.escape(b.title)}</h4>" if b.title else ""
        return f'{title}<div class="poem">{html.escape(b.text)}</div>'
    if isinstance(b, ImageBlock):
        return _image_tag(book, b)
    if isinstance(b, TableBlock):
        rows = []
        for i, r in enumerate(b.rows):
            tag = "th" if i < b.header_rows else "td"
            rows.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in r) + "</tr>")
        cap = f"<caption>{_runs(b.caption)}</caption>" if b.caption else ""
        return f"<table>{cap}{''.join(rows)}</table>"
    if isinstance(b, SceneBreakBlock):
        return f'<p class="scene">{html.escape(b.glyph)}</p>'
    if isinstance(b, PageBreakBlock):
        return '<hr style="page-break-after:always">'
    if isinstance(b, RecipeBlock):
        parts = [f"<h3>{html.escape(b.title)}</h3>"]
        meta = [f"{k}: {html.escape(v)}" for k, v in
                (("Prep", b.prep_time), ("Cook", b.cook_time), ("Serves", b.servings)) if v]
        if meta:
            parts.append(f"<p><em>{' · '.join(meta)}</em></p>")
        if b.description:
            parts.append(f"<p>{html.escape(b.description)}</p>")
        if b.ingredients:
            parts.append("<h4>Ingredients</h4><ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in b.ingredients) + "</ul>")
        if b.instructions:
            parts.append("<h4>Method</h4><ol>" + "".join(f"<li>{html.escape(i)}</li>" for i in b.instructions) + "</ol>")
        if b.notes:
            parts.append(f"<p><strong>Notes:</strong> {html.escape(b.notes)}</p>")
        if b.nutrition:
            parts.append(f"<p><strong>Nutrition (as supplied):</strong> {html.escape(b.nutrition)}</p>")
        return "".join(parts)
    if isinstance(b, ExerciseBlock):
        label = EXERCISE_LABELS.get(b.kind, b.kind.title())
        head = f"{label}: {b.title}" if b.title else label
        return f'<div class="callout"><strong>{html.escape(head)}</strong> {_runs(b.runs)}</div>'
    if isinstance(b, FootnoteBlock):
        return f"<p><small><strong>{html.escape(b.label)}</strong> {_runs(b.runs)}</small></p>"
    return ""


def render_html(book: BookProject) -> str:
    md = book.metadata
    body: list[str] = []
    toc: list[str] = []

    def rec(sections: list[Section], depth: int) -> None:
        for s in sections:
            if not s.enabled or s.kind in GENERATED_KINDS and not s.blocks:
                continue
            lvl = min(depth, 2)
            if s.title and s.show_title:
                toc.append(f'<li style="margin-left:{(depth - 1) * 1.2}em"><a href="#sec-{s.id}">{html.escape(s.title)}</a></li>')
                body.append(f'<section class="chapter" id="sec-{s.id}"><h{lvl}>{html.escape(s.title)}</h{lvl}>')
            else:
                body.append(f'<section id="sec-{s.id}">')
            body.extend(_block(book, b) for b in s.blocks)
            rec(s.children, depth + 1)
            body.append("</section>")

    rec(book.sections, 1)
    sub = f"<p><em>{html.escape(md.subtitle)}</em></p>" if md.subtitle else ""
    return (f'<!DOCTYPE html>\n<html lang="{html.escape(md.language)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{html.escape(md.title)}</title><meta name=\"author\" content=\"{html.escape(md.author, quote=True)}\">"
            f"<style>{CSS}</style></head><body><header><h1>{html.escape(md.title)}</h1>{sub}"
            f"<p>{html.escape(md.author)}</p></header><nav aria-label=\"Contents\"><h2>Contents</h2><ul>"
            f"{''.join(toc)}</ul></nav>{''.join(body)}</body></html>")


def export_html(book: BookProject, path: Path) -> None:
    Path(path).write_text(render_html(book), encoding="utf-8")
