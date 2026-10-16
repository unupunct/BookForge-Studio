"""Turns the semantic book into *flows*: measured, splittable pieces of content.

A Flow is a list of Atoms (the smallest unbreakable units: a line of text, an
image, a table row) with spacing and pagination rules. The paginator places
atoms on pages. Nothing here depends on Qt or on PDF output.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock,
                                     HeadingBlock, ImageBlock, ListBlock, PageBreakBlock,
                                     ParagraphBlock, PoetryBlock, QuoteBlock, RecipeBlock,
                                     Run, SceneBreakBlock, TableBlock, plain_runs, runs_text)
from ..domain.layouts import MM_TO_PT, BookSettings
from ..i18n import exercise_label, tr
from ..domain.sections import GENERATED_KINDS, RECTO_KINDS, Section
from ..domain.styles import ResolvedStyle, StyleSet
from .hyphenation import get_hyphenator
from .measurement import break_lines, place_line, text_width, tokenize
from .model import Glyphs, ImageItem, Item, LayoutIssue, LineItem, RectItem
from .typography import fonts

ACCENT = "#C97B3C"
TOC_EXCLUDED = {"front_cover", "title_page", "copyright", "toc", "back_cover"}


@dataclass
class Atom:
    height: float
    items: list[Item] = field(default_factory=list)  # x from content-left, y from atom top
    gap_before: float = 0.0


@dataclass
class Flow:
    block_id: str | None = None
    atoms: list[Atom] = field(default_factory=list)
    space_before: float = 0.0
    space_after: float = 0.0
    keep_with_next: bool = False
    keep_together: bool = False
    widow: int = 2
    orphan: int = 2
    anchors: list[str] = field(default_factory=list)
    header_atoms: list[Atom] = field(default_factory=list)  # repeated on continuation pages
    own_page: bool = False  # image on a dedicated page
    drop: float = 0.0  # extra space above a chapter opening, kept even at the top of a page
    issues: list[tuple[str, str, str]] = field(default_factory=list)  # severity, code, message
    # control flows: section_start | page_break | full_page | blank_page
    control: str | None = None
    ctl: dict[str, Any] = field(default_factory=dict)

    @property
    def height(self) -> float:
        total = 0.0
        for i, a in enumerate(self.atoms):
            total += a.height + (a.gap_before if i else 0.0)
        return total


@dataclass
class TocEntry:
    level: int
    title: str
    anchor: str


def effective_margins(settings: BookSettings, matter: str) -> tuple[float, float, float, float]:
    """(top, bottom, inner, outer) in points, gutter included in the inner margin."""
    m = settings.margins_for(matter)
    return (m.top * MM_TO_PT, m.bottom * MM_TO_PT,
            (m.inner + settings.gutter_mm) * MM_TO_PT, m.outer * MM_TO_PT)


def content_size(settings: BookSettings, matter: str) -> tuple[float, float]:
    w, h = settings.page_size_pt()
    top, bottom, inner, outer = effective_margins(settings, matter)
    return max(w - inner - outer, 36.0), max(h - top - bottom, 36.0)


class BuildContext:
    def __init__(self, book: BookProject):
        self.book = book
        self.settings = book.settings
        st = self.settings
        # Book-level typography settings are the root of the style hierarchy: every
        # style that inherits from "body" follows them unless it overrides a property.
        defs = dict(book.styles)
        defs["body"] = replace(defs["body"], font_family=st.body_font, font_size=st.body_size,
                               line_height=st.line_height, space_after=st.paragraph_spacing,
                               align="justify" if st.justify else "left",
                               first_indent=st.first_line_indent)
        self.styles = StyleSet(defs)
        self.matter = "main"
        self.width, self.height = content_size(self.settings, "main")
        self.hyphenator = get_hyphenator(book.metadata.language) if st.hyphenate else None
        self.chapter_numbers: dict[str, int] = {}
        n = 0
        for sec in book.walk():
            if sec.enabled and sec.kind == "chapter":
                n += 1
                self.chapter_numbers[sec.id] = n

    def use_matter(self, matter: str) -> None:
        self.matter = matter
        self.width, self.height = content_size(self.settings, matter)

    def style(self, name: str, override: str | None = None) -> ResolvedStyle:
        return self.styles.resolve(override or name)


# --------------------------------------------------------------------- text
def _baseline(leading: float, size: float) -> float:
    return (leading - size) / 2 + size * 0.8


def text_atoms(runs: list[Run], style: ResolvedStyle, ctx: BuildContext, block_id: str | None,
               *, width: float | None = None, left_extra: float = 0.0, bullet: str | None = None,
               align: str | None = None, decorate: bool = True,
               preserve_newlines: bool = False, hyphenate: bool = False) -> list[Atom]:
    width = ctx.width if width is None else width
    left = style.left_indent + left_extra
    right = style.right_indent
    first_x = left + style.first_indent
    first_w = width - right - first_x
    rest_w = width - right - left
    toks = tokenize(runs, style, preserve_newlines=preserve_newlines)
    lines = break_lines(toks, first_w, rest_w, ctx.hyphenator if hyphenate else None)
    leading = style.font_size * style.line_height
    align = align or style.align
    atoms: list[Atom] = []
    for n, line in enumerate(lines):
        x0 = first_x if n == 0 else left
        avail = first_w if n == 0 else rest_w
        items, _ = place_line(line, x0, avail, align, block_id)
        size = max([t.size for t in line.tokens] or [style.font_size])
        base = _baseline(max(leading, size * 1.15), size)
        h = max(leading, size * 1.15)
        for it in items:
            it.y += base
        out: list[Item] = []
        if decorate and style.background:
            out.append(RectItem(left - 4, 0, width - left - right + 8, h, fill=style.background,
                                block_id=block_id))
        if decorate and style.border:
            out.append(LineItem(left - 4, 0, left - 4, h, width=1.5, color=ACCENT,
                                block_id=block_id))
        if bullet and n == 0:
            face = fonts.face(style.font_family, style.bold, style.italic)
            out.append(Glyphs(x=left - left_extra + 2, y=base, text=bullet,
                              font=face.key, size=style.font_size, color=style.color,
                              width=text_width(bullet, style.font_family, style.font_size),
                              block_id=block_id))
        out.extend(items)
        atoms.append(Atom(h, out))
    return atoms


def _flow_from_style(atoms: list[Atom], style: ResolvedStyle, ctx: BuildContext,
                     block_id: str | None, **kw: Any) -> Flow:
    return Flow(block_id=block_id, atoms=atoms, space_before=style.space_before,
                space_after=style.space_after, keep_with_next=style.keep_with_next,
                widow=ctx.settings.widow_lines, orphan=ctx.settings.orphan_lines, **kw)


def paragraph_flow(block: ParagraphBlock, ctx: BuildContext, first: bool) -> Flow:
    style = ctx.style("first_paragraph" if first else "body", block.style)
    over = {k: v for k, v in (("align", block.align or None), ("left_indent", block.left_indent),
                              ("first_indent", block.first_indent),
                              ("space_before", block.space_before),
                              ("space_after", block.space_after)) if v is not None}
    if over:
        style = replace(style, **over)
    if not block.runs:
        atoms = [Atom(style.font_size * style.line_height)]
    else:
        atoms = text_atoms(block.runs, style, ctx, block.id, preserve_newlines=True, hyphenate=True)
    f = _flow_from_style(atoms, style, ctx, block.id)
    f.keep_with_next = f.keep_with_next or block.keep_with_next
    # Short paragraphs are not split across pages.
    f.keep_together = len(atoms) <= 3
    return f


def heading_flow(block: HeadingBlock, ctx: BuildContext) -> Flow:
    level = min(max(block.level, 1), 4)
    style = ctx.style(f"heading{level}", block.style)
    atoms = text_atoms(block.runs, style, ctx, block.id)
    f = _flow_from_style(atoms, style, ctx, block.id, anchors=[f"blk:{block.id}"])
    f.keep_with_next = True
    f.keep_together = True
    return f


def title_flow(text: str, style_name: str, ctx: BuildContext, block_id: str | None,
               anchors: list[str] | None = None) -> Flow:
    style = ctx.style(style_name)
    atoms = text_atoms(plain_runs(text), style, ctx, block_id)
    f = _flow_from_style(atoms, style, ctx, block_id, anchors=anchors or [])
    f.keep_together = True
    f.keep_with_next = True
    return f


def list_flow(block: ListBlock, ctx: BuildContext, first: bool) -> Flow:
    style = ctx.style("body", block.style)
    style.first_indent = 0
    style.align = "left"
    indent = 20.0
    atoms: list[Atom] = []
    for i, item in enumerate(block.items):
        marker = f"{i + 1}." if block.ordered else "•"
        part = text_atoms(item, style, ctx, block.id, left_extra=indent, bullet=marker)
        if part:
            part[0].gap_before = 3.0
        atoms.extend(part)
    f = _flow_from_style(atoms, style, ctx, block.id)
    f.space_before = 4.0
    f.space_after = 6.0
    f.keep_with_next = block.keep_with_next
    return f


def quote_flows(block: QuoteBlock, ctx: BuildContext) -> list[Flow]:
    style = ctx.style("block_quote", block.style)
    flows = [_flow_from_style(text_atoms(block.runs, style, ctx, block.id), style, ctx, block.id)]
    if block.attribution:
        attr_style = replace(style, italic=False, space_before=0, align="right", font_size=style.font_size * 0.92)
        atoms = text_atoms([Run("— " + runs_text(block.attribution))], attr_style, ctx, block.id)
        flows.append(_flow_from_style(atoms, attr_style, ctx, block.id))
        flows[0].keep_with_next = True
        flows[0].space_after = 2
    return flows


def caption_flow(caption: list[Run], ctx: BuildContext, block_id: str | None) -> Flow | None:
    if not caption:
        return None
    style = ctx.style("caption")
    return _flow_from_style(text_atoms(caption, style, ctx, block_id), style, ctx, block_id)


def scene_break_flow(block: SceneBreakBlock, ctx: BuildContext) -> Flow:
    style = ctx.style("scene_break")
    return _flow_from_style(text_atoms([Run(block.glyph)], style, ctx, block.id), style, ctx,
                            block.id)


# --------------------------------------------------------------------- code
def code_flow(block: CodeBlock, ctx: BuildContext) -> list[Flow]:
    style = ctx.style("code", block.style)
    face = fonts.face(style.font_family, style.bold, style.italic)
    leading = style.font_size * style.line_height
    left = style.left_indent
    avail = ctx.width - left - 2 - style.right_indent
    atoms: list[Atom] = []
    wrapped = False
    for raw in block.text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.expandtabs(4)
        chunks: list[str] = []
        cur = ""
        for ch in line:
            if cur and fonts.width(cur + ch, face.key, style.font_size) > avail:
                chunks.append(cur)
                cur = ch
            else:
                cur += ch
        chunks.append(cur)
        wrapped = wrapped or len(chunks) > 1
        for ci, chunk in enumerate(chunks):
            items: list[Item] = [RectItem(left - 4, 0, ctx.width - left + 4 - style.right_indent,
                                          leading, fill=style.background, block_id=block.id)]
            if chunk:
                items.append(Glyphs(x=left, y=_baseline(leading, style.font_size), text=chunk,
                                    font=face.key, size=style.font_size, color=style.color,
                                    width=fonts.width(chunk, face.key, style.font_size),
                                    block_id=block.id, kind="code"))
            atoms.append(Atom(leading, items))
    f = Flow(block_id=block.id, atoms=atoms, space_before=style.space_before,
             space_after=style.space_after, widow=2, orphan=2,
             keep_together=len(atoms) <= 12)
    if wrapped:
        f.issues.append(("info", "code_wrapped",
                         "Long code lines were wrapped to fit the page width"))
    flows = [f]
    cap = caption_flow(block.caption, ctx, block.id)
    if cap:
        f.keep_with_next = True
        flows.append(cap)
    return flows


# ------------------------------------------------------------------- poetry
def _atoms_height(atoms: list[Atom]) -> float:
    return sum(a.height + (a.gap_before if i else 0.0) for i, a in enumerate(atoms))


def poetry_flows(block: PoetryBlock, ctx: BuildContext) -> list[Flow]:
    base = ctx.style("poetry", block.style)
    own_page = block.one_per_page or ctx.settings.poems_new_page
    align = block.align or base.align
    if align not in ("left", "center", "right"):
        align = "left"
    lines = block.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def build(style: ResolvedStyle) -> list[Atom]:
        leading = style.font_size * style.line_height
        stanza_gap = leading * ctx.settings.stanza_gap
        space_w = text_width(" ", style.font_family, style.font_size)
        atoms: list[Atom] = []
        pending_gap = 0.0
        for raw in lines:
            if not raw.strip():
                pending_gap += stanza_gap  # every blank line in the source adds one stanza gap
                continue
            raw = raw.expandtabs(4)
            indent = (len(raw) - len(raw.lstrip(" "))) * space_w if align == "left" else 0.0
            line_atoms = text_atoms(plain_runs(raw.strip()), style, ctx, block.id,
                                    left_extra=min(indent, ctx.width * 0.5), align=align, decorate=False)
            # Wrapped continuation lines get a hanging indent so they read as one line.
            for i, a in enumerate(line_atoms):
                if i > 0:
                    a.items = [it.moved(14, 0) if isinstance(it, Glyphs) else it for it in a.items]
            if line_atoms:
                line_atoms[0].gap_before = pending_gap
            pending_gap = 0.0
            atoms.extend(line_atoms)
        if block.signature.strip():  # printed with the poem's last lines, never alone on a page
            sig_style = replace(style, italic=True, font_size=style.font_size * 0.85, align="right",
                                left_indent=0.0, color="#666666")
            sig = text_atoms(plain_runs(block.signature.strip()), sig_style, ctx, block.id, align="right",
                             decorate=False)
            if sig:
                sig[0].gap_before = leading * 0.6
                atoms.extend(sig)
        return atoms

    flows: list[Flow] = []
    title_h = 0.0
    if block.title:
        tstyle = ctx.style("poetry_title")
        t = _flow_from_style(text_atoms(plain_runs(block.title), tstyle, ctx, block.id), tstyle, ctx,
                             block.id)
        t.keep_with_next = True
        t.keep_together = True
        t.anchors = [f"blk:{block.id}"]
        flows.append(t)
        title_h = t.height + t.space_after + 6
    style = base
    atoms = build(style)
    tightened = False
    if own_page:
        # A poem that owns its page and only just overflows is tightened (leading reduced, never
        # below 1.2) so it does not leave two stray lines on a second page.
        avail = ctx.height - title_h - 14
        lh = style.line_height
        while _atoms_height(atoms) > avail and lh > 1.2 + 1e-6:
            lh = max(lh - 0.03, 1.2)
            style = replace(base, line_height=lh)
            atoms = build(style)
            tightened = True
        if _atoms_height(atoms) > avail:  # does not fit even tightened: split normally, restore spacing
            style, atoms, tightened = base, build(base), False
    leading = style.font_size * style.line_height
    header: list[Atom] = []
    if block.continuation_marker:
        cont_text = tr("continued", ctx.book.metadata.language)
        face = fonts.face(style.font_family, False, True)
        sz = style.font_size * 0.85
        h = sz * 1.5
        header = [Atom(h, [Glyphs(x=style.left_indent, y=_baseline(h, sz), text=cont_text,
                                  font=face.key, size=sz, color="#666666",
                                  width=fonts.width(cont_text, face.key, sz),
                                  block_id=block.id)])]
    f = Flow(block_id=block.id, atoms=atoms, space_before=style.space_before + 6,
             space_after=style.space_after + 12, widow=4 if own_page else 2, orphan=2,
             header_atoms=header, keep_together=True,
             anchors=[] if block.title else [f"blk:{block.id}"])
    if own_page:
        flows.insert(0, Flow(control="page_break", ctl={"blank": False, "recto": False}))
        tail = Flow(control="page_break", ctl={"blank": False, "recto": False})
        flows.append(f)
        flows.append(tail)
        f.issues.append(("info", "poem_page", "Poem placed on its own page"))
        if tightened:
            f.issues.append(("info", "poem_tightened",
                             f"Line spacing of a poem was tightened to {style.line_height:.2f} to fit one page"))
    else:
        flows.append(f)
    f.ctl["poem"] = True
    return flows


# -------------------------------------------------------------------- table
def table_flows(block: TableBlock, ctx: BuildContext) -> list[Flow]:
    rows = [list(r) for r in block.rows if r is not None]
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    rows = [r + [""] * (ncols - len(r)) for r in rows]
    weights = block.col_widths if block.col_widths and len(block.col_widths) == ncols else [1.0] * ncols
    total = sum(weights) or 1.0
    widths = [ctx.width * w / total for w in weights]
    xs = [sum(widths[:i]) for i in range(ncols)]
    pad = 4.0
    body = ctx.style("table")
    head = ctx.style("table_header")
    atoms: list[Atom] = []
    for ri, row in enumerate(rows):
        style = head if ri < block.header_rows else body
        cells: list[list[Atom]] = []
        for ci, text in enumerate(row):
            align = (block.align[ci] if block.align and ci < len(block.align) else "left")
            cstyle = replace(style, first_indent=0, left_indent=0, right_indent=0,
                             background=None, border=False)
            cells.append(text_atoms(plain_runs(text), cstyle, ctx, block.id,
                                    width=widths[ci] - 2 * pad, align=align, decorate=False))
        leading = style.font_size * style.line_height
        h = max([sum(a.height for a in c) for c in cells] + [leading]) + 2 * pad
        items: list[Item] = []
        for ci, cell in enumerate(cells):
            items.append(RectItem(xs[ci], 0, widths[ci], h, fill=style.background,
                                  stroke="#8A8A8A", stroke_width=0.5, block_id=block.id))
            y = pad
            for a in cell:
                for it in a.items:
                    if isinstance(it, Glyphs):
                        items.append(it.moved(xs[ci] + pad, y))
                y += a.height
        atoms.append(Atom(h, items))
    flow = Flow(block_id=block.id, atoms=atoms, space_before=6, space_after=8,
                widow=1, orphan=min(block.header_rows + 1, len(atoms)),
                header_atoms=atoms[:block.header_rows] if block.header_rows else [])
    # Rows that cannot fit a whole page are reported by the paginator as overflow.
    flows = [flow]
    cap = caption_flow(block.caption, ctx, block.id)
    if cap:
        flow.keep_with_next = False
        # keep the caption with the last row: append as atoms of the same flow
        for i, a in enumerate(cap.atoms):
            a.gap_before = 4 if i == 0 else 0
            flow.atoms.append(a)
    return flows


# -------------------------------------------------------------------- image
def image_flow(block: ImageBlock, ctx: BuildContext) -> Flow:
    book = ctx.book
    asset = book.assets.get(block.asset)
    flow = Flow(block_id=block.id, space_before=8, space_after=8, widow=1, orphan=1,
                keep_together=True)
    caption_atoms: list[Atom] = []
    if block.caption:
        cap = caption_flow(block.caption, ctx, block.id)
        if cap:
            caption_atoms = cap.atoms
    cap_h = sum(a.height for a in caption_atoms) + (6 if caption_atoms else 0)
    max_w = ctx.width * min(max(block.width_pct, 5.0), 100.0) / 100.0
    missing = asset is None or not asset.data
    if missing:
        flow.issues.append(("error", "missing_asset",
                            f"Image asset is missing or empty (id {block.asset or 'none'})"))
        aspect = 0.6
    else:
        iw, ih = asset.width or 1, asset.height or 1
        if block.crop and len(block.crop) == 4:
            l, t, r, b = block.crop
            iw, ih = iw * max(r - l, 0.01), ih * max(b - t, 0.01)
        aspect = ih / iw
    w = max_w
    h = w * aspect
    limit = ctx.height - cap_h - (0 if block.own_page else 0)
    if h > limit:
        scale = limit / h
        w, h = w * scale, limit
        flow.issues.append(("warning", "image_scaled",
                            "Image was reduced (aspect ratio kept) to fit the page"))
    x = {"left": 0.0, "right": ctx.width - w}.get(block.align, (ctx.width - w) / 2)
    items: list[Item] = []
    crop = tuple(block.crop) if block.crop and len(block.crop) == 4 else None
    items.append(ImageItem(x, 0, w, h, block.asset, crop, block.alt, block.id, missing))
    if missing:
        items.append(RectItem(x, 0, w, h, fill="#EEEEEE", stroke="#B04040", block_id=block.id))
        face = fonts.face("sans")
        items.append(Glyphs(x + 8, h / 2, "[Missing image]", face.key, 10, "#B04040",
                            width=fonts.width("[Missing image]", face.key, 10), block_id=block.id))
    atoms_h = h
    atom_items = items
    if caption_atoms:
        y = h + 6
        for a in caption_atoms:
            for it in a.items:
                atom_items.append(it.moved(0, y))
            y += a.height
        atoms_h = y
    flow.atoms = [Atom(atoms_h, atom_items)]
    flow.own_page = block.own_page
    return flow


# ------------------------------------------------------------- composites
EXERCISE_LABELS = {"objective": "Learning objective", "definition": "Definition",
                   "example": "Example", "exercise": "Exercise", "question": "Question",
                   "answer": "Answer", "note": "Note", "warning": "Warning",
                   "reference": "Reference"}


def exercise_flow(block: ExerciseBlock, ctx: BuildContext) -> Flow:
    style = ctx.style("callout", block.style)
    label = exercise_label(block.kind, ctx.book.metadata.language)
    head = f"{label}: {block.title}" if block.title else label
    runs = [Run(head + ("  " if block.runs else ""), bold=True), *block.runs]
    f = _flow_from_style(text_atoms(runs, style, ctx, block.id), style, ctx, block.id)
    f.keep_together = len(f.atoms) <= 8
    return f


def recipe_flows(block: RecipeBlock, ctx: BuildContext) -> list[Flow]:
    lang = ctx.book.metadata.language
    flows: list[Flow] = []
    if block.title:
        flows.append(title_flow(block.title, "recipe_heading", ctx, block.id,
                                [f"blk:{block.id}"]))
    meta = []
    if block.prep_time:
        meta.append(f"{tr('prep', lang)}: {block.prep_time}")
    if block.cook_time:
        meta.append(f"{tr('cook', lang)}: {block.cook_time}")
    if block.servings:
        meta.append(f"{tr('serves', lang)}: {block.servings}")
    body = ctx.style("body")
    body.first_indent = 0
    body.align = "left"
    if meta:
        flows.append(_flow_from_style(text_atoms([Run("   ·   ".join(meta), italic=True)],
                                                 body, ctx, block.id), body, ctx, block.id))
    if block.image:
        flows.append(image_flow(ImageBlock(asset=block.image, width_pct=70,
                                           alt=block.title), ctx))
    if block.description:
        flows.append(_flow_from_style(text_atoms(plain_runs(block.description), body, ctx,
                                                 block.id), body, ctx, block.id))
    if block.ingredients:
        flows.append(title_flow(tr("ingredients", lang), "heading3", ctx, block.id))
        flows.append(list_flow(ListBlock(ordered=False, items=[plain_runs(i) for i in
                                                               block.ingredients]), ctx, False))
    if block.instructions:
        flows.append(title_flow(tr("method", lang), "heading3", ctx, block.id))
        flows.append(list_flow(ListBlock(ordered=True, items=[plain_runs(i) for i in
                                                              block.instructions]), ctx, False))
    if block.notes:
        flows.append(_flow_from_style(text_atoms([Run(tr("recipe_notes", lang) + ": ", bold=True), Run(block.notes)],
                                                 body, ctx, block.id), body, ctx, block.id))
    if block.nutrition:
        flows.append(_flow_from_style(text_atoms([Run(tr("nutrition", lang) + ": ", bold=True),
                                                  Run(block.nutrition)], body, ctx, block.id),
                                      body, ctx, block.id))
    return flows


def footnote_flow(block: FootnoteBlock, ctx: BuildContext) -> Flow:
    style = ctx.style("footnote", block.style)
    runs = ([Run(block.label + " ", bold=True)] if block.label else []) + block.runs
    return _flow_from_style(text_atoms(runs, style, ctx, block.id), style, ctx, block.id)


def block_flows(block: Block, ctx: BuildContext, first: bool) -> list[Flow]:
    if isinstance(block, ParagraphBlock):
        return [paragraph_flow(block, ctx, first)]
    if isinstance(block, HeadingBlock):
        return [heading_flow(block, ctx)]
    if isinstance(block, ListBlock):
        return [list_flow(block, ctx, first)]
    if isinstance(block, QuoteBlock):
        return quote_flows(block, ctx)
    if isinstance(block, CodeBlock):
        return code_flow(block, ctx)
    if isinstance(block, PoetryBlock):
        return poetry_flows(block, ctx)
    if isinstance(block, TableBlock):
        return table_flows(block, ctx)
    if isinstance(block, ImageBlock):
        return [image_flow(block, ctx)]
    if isinstance(block, SceneBreakBlock):
        return [scene_break_flow(block, ctx)]
    if isinstance(block, PageBreakBlock):
        return [Flow(block_id=block.id, control="page_break",
                     ctl={"blank": block.blank, "recto": block.recto})]
    if isinstance(block, RecipeBlock):
        return recipe_flows(block, ctx)
    if isinstance(block, ExerciseBlock):
        return [exercise_flow(block, ctx)]
    if isinstance(block, FootnoteBlock):
        return [footnote_flow(block, ctx)]
    return []


# ----------------------------------------------------------------- sections
def collect_toc(book: BookProject) -> list[TocEntry]:
    settings = book.settings
    entries: list[TocEntry] = []

    def rec(sections: list[Section], depth: int) -> None:
        for s in sections:
            if not s.enabled:
                continue
            if s.kind not in TOC_EXCLUDED and s.in_toc and s.show_title and s.title.strip() \
                    and depth <= settings.toc_depth:
                entries.append(TocEntry(depth, s.title, f"sec:{s.id}"))
            for b in s.blocks:
                if isinstance(b, HeadingBlock) and b.in_toc and b.runs:
                    lvl = depth + b.level
                    if lvl <= settings.toc_depth:
                        entries.append(TocEntry(lvl, runs_text(b.runs), f"blk:{b.id}"))
            rec(s.children, depth + 1)

    rec(book.sections, 1)
    return entries


def poem_entries(book: BookProject) -> list[TocEntry]:
    """One entry per poem for the optional list of poems (titles or first lines)."""
    mode = book.settings.poem_index
    if mode == "none":
        return []
    out: list[TocEntry] = []
    for s in book.walk():
        if not s.enabled:
            continue
        for b in s.blocks:
            if not isinstance(b, PoetryBlock):
                continue
            first = next((l.strip() for l in b.text.splitlines() if l.strip()), "")
            title = b.title.strip()
            short = len(title) <= 4 and title.replace(".", "").isdigit()
            if mode == "first_lines":
                text = f"{title}. {first}" if short and first else (first or title)
            else:
                text = (f"{title}. {first}" if short and first else title) or first
            if text:
                out.append(TocEntry(1, text, f"blk:{b.id}"))
    return out


def outline_entries(book: BookProject) -> list[TocEntry]:
    """Every heading, for PDF bookmarks (independent of the printed TOC depth)."""
    out: list[TocEntry] = []

    def rec(sections: list[Section], depth: int) -> None:
        for s in sections:
            if not s.enabled:
                continue
            if s.kind not in ("front_cover", "back_cover", "copyright") and s.title.strip():
                out.append(TocEntry(min(depth, 4), s.title, f"sec:{s.id}"))
            for b in s.blocks:
                if isinstance(b, HeadingBlock) and b.runs:
                    out.append(TocEntry(min(depth + b.level, 5), runs_text(b.runs), f"blk:{b.id}"))
            rec(s.children, depth + 1)

    rec(book.sections, 1)
    return out


def toc_flows(book: BookProject, ctx: BuildContext, labels: dict[str, str]) -> list[Flow]:
    entries = collect_toc(book)
    poems = poem_entries(book)
    if poems:
        entries = entries + [TocEntry(0, tr("poem_index", book.metadata.language), "")] + poems
    settings = book.settings
    flows: list[Flow] = []
    dot_face = fonts.face("serif")
    for e in entries:
        heading = e.level == 0  # the "Index of poems" heading has no page number or link
        style = ctx.style("toc_entry")
        indent = max(e.level - 1, 0) * 16.0
        size = style.font_size
        leading = size * style.line_height
        face = fonts.face(style.font_family, bold=(e.level <= 1 and (heading or e.anchor.startswith("sec:"))),
                          italic=False)
        label = labels.get(e.anchor, "0") if settings.toc_page_numbers and not heading else ""
        lab_w = fonts.width(label, face.key, size) if label else 0.0
        avail = ctx.width - indent - lab_w - 14
        runs = plain_runs(e.title)
        toks = tokenize(runs, replace(style, bold=(e.level <= 1 and (heading or e.anchor.startswith("sec:")))))
        lines = break_lines(toks, avail, avail)
        atoms: list[Atom] = []
        for n, line in enumerate(lines):
            items, nat = place_line(line, indent, avail, "left", None)
            base = _baseline(leading, size)
            for it in items:
                it.y = base
                it.link = None if heading else f"#{e.anchor}"
            if n == len(lines) - 1 and label:
                dot_w = fonts.width(". ", dot_face.key, size)
                gap = ctx.width - lab_w - (indent + nat) - 8
                count = int(gap // dot_w) if dot_w else 0
                if count > 0:
                    dots = ". " * count
                    items.append(Glyphs(x=ctx.width - lab_w - 4 - fonts.width(dots, dot_face.key, size),
                                        y=base, text=dots, font=dot_face.key, size=size,
                                        color="#777777",
                                        width=fonts.width(dots, dot_face.key, size)))
                items.append(Glyphs(x=ctx.width - lab_w, y=base, text=label, font=face.key,
                                    size=size, color=style.color, width=lab_w,
                                    link=f"#{e.anchor}"))
            atoms.append(Atom(leading, list(items)))
        f = Flow(atoms=atoms, space_before=(14 if heading else 8 if e.level == 1 and e.anchor.startswith("sec:") else 0),
                 space_after=style.space_after,
                 widow=1, orphan=1, keep_together=True)
        flows.append(f)
    return flows


def title_page_flows(book: BookProject, ctx: BuildContext) -> list[Flow]:
    md = book.metadata
    flows: list[Flow] = []
    spacer = Flow(atoms=[Atom(ctx.height * 0.22)], widow=1, orphan=1)
    flows.append(spacer)
    for text, style in ((md.title, "book_title"), (md.subtitle, "subtitle"),
                        (md.author, "author"), (md.publisher, "header_footer")):
        if text.strip():
            f = title_flow(text, style, ctx, None)
            f.keep_with_next = False
            if style == "author":
                f.space_before = 40
            flows.append(f)
            if style == "book_title":  # the template's chapter ornament also marks the title page
                orn = _ornament_flow(book.settings.chapter_ornament, ctx)
                if orn is not None:
                    orn.space_before, orn.keep_with_next = 6, False
                    flows.append(orn)
    return flows


def copyright_flows(book: BookProject, ctx: BuildContext) -> list[Flow]:
    md = book.metadata
    lines: list[str] = []
    if md.author.strip():
        lines.append(f"© {md.year} {md.author}".replace("  ", " ").strip())
    if md.rights.strip():
        lines.extend(md.rights.splitlines())
    if md.publisher.strip():
        lines.append(md.publisher)
    if md.isbn.strip():
        lines.append(f"ISBN {md.isbn}")
    if not lines:
        return [Flow(control="blank_page")]
    flows = [Flow(atoms=[Atom(ctx.height * 0.55)], widow=1, orphan=1)]
    style = ctx.style("footnote")
    style.align = "left"
    for ln in lines:
        flows.append(_flow_from_style(text_atoms(plain_runs(ln), style, ctx, None), style, ctx, None))
    return flows


def cover_items(book: BookProject, W: float, H: float, back: bool) -> list[Item]:
    """Front or back cover. A layered design wins; otherwise the simple form fields generate it."""
    cv = book.settings.cover
    layers = cv.back_layers if back else cv.front_layers
    if layers:
        from .cover_builder import side_items
        if back:
            return side_items(book, layers, W, H, cv.back_background or cv.background,
                              None if cv.back_background else cv.background2)
        return side_items(book, layers, W, H, cv.background, cv.background2)
    return _legacy_cover_items(book, W, H, back)


def _legacy_cover_items(book: BookProject, W: float, H: float, back: bool) -> list[Item]:
    cv = book.settings.cover
    md = book.metadata
    items: list[Item] = [RectItem(0, 0, W, H, fill=cv.background, gradient_to=cv.background2)]
    asset = book.assets.get(cv.image_asset) if cv.image_asset else None
    if asset and asset.data and not back:
        iw, ih = asset.width or 1, asset.height or 1
        if cv.image_mode == "behind":
            # centre-crop to fill the page without distortion
            target = W / H
            src = iw / ih
            if src > target:
                f = target / src
                crop = ((1 - f) / 2, 0.0, (1 + f) / 2, 1.0)
            else:
                f = src / target
                crop = (0.0, (1 - f) / 2, 1.0, (1 + f) / 2)
            items.append(ImageItem(0, 0, W, H, asset.id, crop, "Cover image"))
        else:
            w = W * 0.8
            h = min(w * ih / iw, H * 0.45)
            w = h * iw / ih
            items.append(ImageItem((W - w) / 2, H * 0.08, w, h, asset.id, None, "Cover image"))
    face_t = fonts.face(cv.font_family, bold=True)
    face_n = fonts.face(cv.font_family)

    def centered(text: str, face_key: str, size: float, color: str, y: float) -> float:
        toks = tokenize([Run(text)], ResolvedStyle("cover", font_family=cv.font_family,
                                                   font_size=size, color=color,
                                                   bold=(face_key == face_t.key)))
        margin = W * 0.12
        lines = break_lines(toks, W - 2 * margin, W - 2 * margin)
        for ln in lines:
            gl, _ = place_line(ln, margin, W - 2 * margin, "center", None)
            for g in gl:
                g.y = y + size
                items.append(g)
            y += size * 1.25
        return y

    if back:
        y = H * 0.2
        for para in (cv.back_text or "").split("\n"):
            if para.strip():
                y = centered(para, face_n.key, 11, cv.title_color, y) + 8
        if cv.publisher_text or md.publisher:
            centered(cv.publisher_text or md.publisher, face_n.key, 10, cv.author_color, H * 0.88)
    else:
        y = centered(md.title, face_t.key, cv.title_size, cv.title_color, H * 0.28)
        if md.subtitle:
            y = centered(md.subtitle, face_n.key, cv.subtitle_size, cv.title_color, y + 10)
        if md.author:
            centered(md.author, face_n.key, cv.author_size, cv.author_color, H * 0.84)
    return items


def to_roman_upper(n: int) -> str:
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
            (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, t in vals:
        while n >= v:
            out += t
            n -= v
    return out


def _ornament_flow(kind: str, ctx: BuildContext) -> Flow | None:
    """A small decoration under chapter titles (rule or a centred glyph string)."""
    if kind in ("", "none"):
        return None
    if kind == "rule":
        w = ctx.width * 0.18
        x = (ctx.width - w) / 2
        return Flow(atoms=[Atom(10, [LineItem(x, 5, x + w, 5, 0.8, "#777777")])], space_after=18,
                    widow=1, orphan=1, keep_with_next=True)
    glyph = {"dots": "·  ·  ·", "stars": "*   *   *", "bullet": "•",
             "dash": "—"}.get(kind)
    if not glyph:
        return None
    style = ctx.style("scene_break")
    f = _flow_from_style(text_atoms([Run(glyph)], style, ctx, None), style, ctx, None)
    f.space_before, f.space_after, f.keep_with_next = 0, 18, True
    return f


def section_flows(book: BookProject, ctx: BuildContext, section: Section, depth: int,
                  labels: dict[str, str]) -> list[Flow]:
    """All flows of a section (and its children), beginning with a control flow."""
    s = book.settings
    ctx.use_matter(section.matter)
    flows: list[Flow] = []
    kind = section.kind

    chapter_like = kind not in ("section",)
    new_page = section.new_page
    if new_page is None:
        new_page = s.chapter_new_page if chapter_like else False
        if kind in ("title_page", "copyright", "toc", "dedication", "front_cover", "back_cover"):
            new_page = True
    recto = False
    if s.facing_pages:
        recto = (kind in RECTO_KINDS and kind != "part") or \
                (kind in ("chapter", "part", "appendix", "glossary", "bibliography", "index",
                          "acknowledgments", "back_matter") and s.chapter_right_page)
        if kind == "part":
            recto = True
    flows.append(Flow(control="section_start",
                      ctl={"section_id": section.id, "title": section.title, "matter": section.matter,
                           "kind": kind, "new_page": new_page, "recto": recto,
                           "opening": kind not in ("section",)}))

    if kind == "front_cover" or kind == "back_cover":
        W, H = s.page_size_pt()
        flows.append(Flow(control="full_page", ctl={"items": cover_items(book, W, H, kind == "back_cover")}))
        return flows

    if kind == "title_page" and not section.blocks:
        flows.extend(title_page_flows(book, ctx))
    elif kind == "copyright" and not section.blocks:
        flows.extend(copyright_flows(book, ctx))
    elif kind == "toc":
        if section.title and section.show_title:
            flows.append(title_flow(section.title, "toc_title", ctx, None, [f"sec:{section.id}"]))
        flows.extend(toc_flows(book, ctx, labels))
    elif section.title and section.show_title and kind != "title_page":
        style_name = {"part": "part_title", "section": f"heading{min(depth, 4)}"}.get(kind, "chapter_title")
        tf = title_flow(section.title, style_name, ctx, None, [f"sec:{section.id}"])
        opening = bool(new_page) and kind != "section"  # the drop only applies on a fresh page
        num = ctx.chapter_numbers.get(section.id)
        if kind == "chapter" and num and s.chapter_number_style != "none":
            n_text = to_roman_upper(num) if s.chapter_number_style == "roman" else str(num)
            pattern = s.chapter_label
            lang = book.metadata.language
            for key, english in (("chapter", "Chapter"), ("part", "Part")):  # built-in labels follow the language
                if pattern.startswith(english + " "):
                    pattern = tr(key, lang) + pattern[len(english):]
            label = title_flow(pattern.replace("{n}", n_text), "chapter_label", ctx, None)
            label.drop = s.chapter_drop if opening else 0.0
            tf.space_before = 2.0
            flows.append(label)
        elif opening:
            tf.drop = s.chapter_drop
        flows.append(tf)
        orn = _ornament_flow(s.chapter_ornament, ctx) if kind == "chapter" else None
        if orn:
            tf.space_after = max(tf.space_after * 0.4, 6.0)
            flows.append(orn)
    else:
        if section.title:
            flows.append(Flow(control="anchor", ctl={"anchor": f"sec:{section.id}"}))

    first = True
    for b in section.blocks:
        bf = block_flows(b, ctx, first)
        flows.extend(bf)
        if isinstance(b, (ParagraphBlock,)) and b.runs:
            first = False
        elif isinstance(b, (HeadingBlock, SceneBreakBlock, PageBreakBlock)):
            first = True
        elif bf:
            first = False
    for child in section.children:
        if child.enabled:
            flows.extend(section_flows(book, ctx, child, depth + 1, labels))
    return flows


def section_signature(book: BookProject, section: Section) -> str:
    h = hashlib.sha1()
    h.update(json.dumps(section.to_dict(), sort_keys=True, default=str).encode())
    return h.hexdigest()


def styles_signature(book: BookProject) -> str:
    h = hashlib.sha1()
    h.update(json.dumps({k: v.to_dict() for k, v in sorted(book.styles.items())},
                        sort_keys=True, default=str).encode())
    h.update(json.dumps(book.settings.to_dict(), sort_keys=True, default=str).encode())
    h.update(json.dumps(book.metadata.to_dict(), sort_keys=True).encode())
    h.update(json.dumps(sorted((a.id, a.sha256, a.width, a.height, bool(a.data))
                               for a in book.assets.values())).encode())
    return h.hexdigest()
