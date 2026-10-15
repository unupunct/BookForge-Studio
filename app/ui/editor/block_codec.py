"""Two-way conversion between the semantic block model and a QTextDocument.

The QTextDocument is only a *view* of one section's blocks: the structured model
stays the source of truth. Every QTextBlock carries its semantic kind and the id
of the model block it belongs to, so unedited properties (captions, image
assets, poem titles ...) are preserved when text is edited.
"""
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextListFormat)

from ...domain.book import BookProject
from ...domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                      ImageBlock, ListBlock, PageBreakBlock, ParagraphBlock,
                                      PoetryBlock, QuoteBlock, RecipeBlock, Run, SceneBreakBlock,
                                      TableBlock, merge_runs, new_id, runs_text)
from ...layout.page_builder import EXERCISE_LABELS
from .. import theme

_UP = int(QTextFormat.UserProperty)
P_KIND, P_ID, P_LEVEL, P_DATA, P_KWN, P_STYLE, P_ALIGN = (_UP + i for i in range(1, 8))
P_CODE = _UP + 10
LINE_SEP = " "

PLACEHOLDER_KINDS = {"placeholder"}
LIST_KINDS = {"list_bullet", "list_number"}
EDITOR_FONT = "Georgia"
CODE_FONT = "Consolas"
HEADING_SIZES = {1: 22, 2: 18, 3: 15, 4: 13, 5: 12, 6: 12}
LINK_COLOR = QColor(theme.ACCENT_HI)


def _text_color() -> QColor:
    return QColor(theme.TEXT)


def char_format(kind: str, level: int, run: Run | None = None) -> QTextCharFormat:
    f = QTextCharFormat()
    family, size, bold, italic = EDITOR_FONT, 12.0, False, False
    color = _text_color()
    if kind == "heading":
        size, bold = HEADING_SIZES.get(level, 13), True
        family = "Segoe UI"
    elif kind == "quote":
        italic = True
        color = QColor(theme.TEXT_MUTED).lighter(125)
    elif kind in ("code", "poem_title_unused"):
        family, size = CODE_FONT, 10.5
    elif kind == "poem_title":
        bold = True
    elif kind == "quote_attr":
        size, italic = 11, False
        color = QColor(theme.TEXT_MUTED)
    elif kind == "placeholder":
        family, size, italic = "Segoe UI", 10.5, True
        color = QColor(theme.ACCENT_HI)
    elif kind == "scene":
        color = QColor(theme.TEXT_MUTED)
    elif kind == "exercise":
        size = 11.5
    elif kind == "footnote":
        size = 10.5
    f.setFontFamilies([family])
    f.setFontPointSize(size)
    f.setFontWeight(QFont.Bold if bold else QFont.Normal)
    f.setFontItalic(italic)
    f.setForeground(QBrush(color))
    if run is not None:
        if run.bold and kind != "heading":
            f.setFontWeight(QFont.Bold)
        if run.italic and kind != "quote":
            f.setFontItalic(True)
        if run.underline:
            f.setFontUnderline(True)
        if run.strike:
            f.setFontStrikeOut(True)
        if run.sup:
            f.setVerticalAlignment(QTextCharFormat.AlignSuperScript)
        elif run.sub:
            f.setVerticalAlignment(QTextCharFormat.AlignSubScript)
        if run.code and kind != "code":
            f.setFontFamilies([CODE_FONT])
            f.setProperty(P_CODE, True)
            f.setBackground(QBrush(QColor(theme.SURFACE_HI)))
        if run.link:
            f.setAnchor(True)
            f.setAnchorHref(run.link)
            f.setForeground(QBrush(LINK_COLOR))
            f.setFontUnderline(True)
    return f


def block_format(kind: str, level: int = 1) -> QTextBlockFormat:
    bf = QTextBlockFormat()
    bf.setBottomMargin(8)
    if kind == "heading":
        bf.setTopMargin(10)
        bf.setBottomMargin(6)
    elif kind == "quote":
        bf.setLeftMargin(28)
        bf.setRightMargin(20)
    elif kind == "quote_attr":
        bf.setLeftMargin(28)
        bf.setAlignment(Qt.AlignRight)
    elif kind == "code":
        bf.setBackground(QBrush(QColor(theme.SURFACE_HI)))
        bf.setLeftMargin(6)
    elif kind in ("poetry", "poem_title"):
        bf.setLeftMargin(28)
        bf.setBottomMargin(10 if kind == "poem_title" else 14)
    elif kind == "scene":
        bf.setAlignment(Qt.AlignHCenter)
    elif kind == "placeholder":
        bf.setBackground(QBrush(QColor(theme.SURFACE)))
        bf.setLeftMargin(10)
    elif kind == "exercise":
        bf.setBackground(QBrush(QColor("#2E2A24")))
        bf.setLeftMargin(10)
    elif kind in LIST_KINDS:
        bf.setBottomMargin(2)
    return bf


# ------------------------------------------------------------------ model -> doc
def placeholder_text(block: Block, book: BookProject | None) -> str:
    if isinstance(block, ImageBlock):
        a = book.assets.get(block.asset) if book else None
        name = a.filename if a else "missing image"
        cap = runs_text(block.caption)
        return f"[Image: {name}]" + (f"  —  {cap}" if cap else "") + "   (double-click to edit)"
    if isinstance(block, TableBlock):
        cols = max((len(r) for r in block.rows), default=0)
        cap = runs_text(block.caption)
        return f"[Table: {len(block.rows)} rows × {cols} columns]" + \
            (f"  —  {cap}" if cap else "") + "   (double-click to edit)"
    if isinstance(block, PageBreakBlock):
        extra = " (blank page)" if block.blank else ""
        extra += " to right-hand page" if block.recto else ""
        return f"───  Page break{extra}  ───"
    if isinstance(block, RecipeBlock):
        return f"[Recipe: {block.title or 'untitled'}]   (double-click to edit)"
    return f"[{block.type}]"


class _Spec:
    __slots__ = ("kind", "id", "level", "data", "runs", "text", "kwn", "style", "align", "fmt")

    def __init__(self, kind: str, id: str, runs: list[Run] | None = None, text: str = "",
                 level: int = 1, data: dict | None = None, kwn: bool = False,
                 style: str | None = None, align: str = "", fmt: dict | None = None):
        self.kind, self.id, self.runs, self.text = kind, id, runs, text
        self.level, self.data, self.kwn, self.style = level, data or {}, kwn, style
        self.align, self.fmt = align, fmt or {}


def _specs_for(block: Block, book: BookProject | None) -> list[_Spec]:
    kw = dict(kwn=block.keep_with_next, style=block.style)
    if isinstance(block, ParagraphBlock):
        fmt = {k: getattr(block, k) for k in ("left_indent", "first_indent", "space_before",
                                              "space_after") if getattr(block, k) is not None}
        return [_Spec("paragraph", block.id, block.runs, align=block.align, fmt=fmt, **kw)]
    if isinstance(block, HeadingBlock):
        return [_Spec("heading", block.id, block.runs, level=block.level, **kw)]
    if isinstance(block, ListBlock):
        kind = "list_number" if block.ordered else "list_bullet"
        return [_Spec(kind, block.id, it, **kw) for it in block.items] or \
            [_Spec(kind, block.id, [], **kw)]
    if isinstance(block, QuoteBlock):
        out = [_Spec("quote", block.id, block.runs, **kw)]
        if block.attribution:
            out.append(_Spec("quote_attr", block.id, block.attribution))
        return out
    if isinstance(block, CodeBlock):
        return [_Spec("code", block.id, text=block.text, **kw)]
    if isinstance(block, PoetryBlock):
        out = []
        if block.title:
            out.append(_Spec("poem_title", block.id, text=block.title))
        out.append(_Spec("poetry", block.id, text=block.text, align=block.align, **kw))
        return out
    if isinstance(block, SceneBreakBlock):
        return [_Spec("scene", block.id, text=block.glyph)]
    if isinstance(block, ExerciseBlock):
        return [_Spec("exercise", block.id, block.runs,
                      data={"kind": block.kind, "title": block.title}, **kw)]
    if isinstance(block, FootnoteBlock):
        return [_Spec("footnote", block.id, block.runs, data={"label": block.label})]
    return [_Spec("placeholder", block.id, text=placeholder_text(block, book))]


def _apply_block_props(cursor: QTextCursor, spec: _Spec) -> None:
    bf = block_format(spec.kind, spec.level)
    bf.setProperty(P_KIND, spec.kind)
    bf.setProperty(P_ID, spec.id)
    bf.setProperty(P_LEVEL, spec.level)
    bf.setProperty(P_KWN, spec.kwn)
    if spec.align:
        bf.setProperty(P_ALIGN, spec.align)
        bf.setAlignment({"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight,
                         "justify": Qt.AlignJustify}.get(spec.align, Qt.AlignLeft))
    if spec.fmt:  # imported paragraph formatting is shown approximately (1 pt ~ 1.33 px)
        if spec.fmt.get("left_indent") is not None:
            bf.setLeftMargin(spec.fmt["left_indent"] * 1.33)
        if spec.fmt.get("first_indent") is not None:
            bf.setTextIndent(spec.fmt["first_indent"] * 1.33)
        if spec.fmt.get("space_before") is not None:
            bf.setTopMargin(spec.fmt["space_before"] * 1.33)
        if spec.fmt.get("space_after") is not None:
            bf.setBottomMargin(spec.fmt["space_after"] * 1.33)
    if spec.style:
        bf.setProperty(P_STYLE, spec.style)
    if spec.data:
        bf.setProperty(P_DATA, json.dumps(spec.data))
    cursor.mergeBlockFormat(bf)


def load_blocks(doc: QTextDocument, blocks: list[Block], book: BookProject | None) -> None:
    doc.clear()
    doc.setUndoRedoEnabled(False)
    cursor = QTextCursor(doc)
    specs: list[_Spec] = []
    for b in blocks:
        specs.extend(_specs_for(b, book))
    if not specs:
        specs = [_Spec("paragraph", new_id(), [])]
    prev: _Spec | None = None
    for spec in specs:
        continuing = (prev is not None and spec.kind in LIST_KINDS and prev.kind == spec.kind
                      and prev.id == spec.id)
        if prev is not None:
            if continuing:
                cursor.insertBlock()  # inherits membership of the current list
            else:
                cursor.insertBlock(QTextBlockFormat(), QTextCharFormat())
        if spec.kind in LIST_KINDS:
            if not continuing:
                lf = QTextListFormat()
                lf.setStyle(QTextListFormat.ListDecimal if spec.kind == "list_number"
                            else QTextListFormat.ListDisc)
                lf.setIndent(1)
                cursor.createList(lf)
        else:
            cursor.setBlockFormat(QTextBlockFormat())
        _apply_block_props(cursor, spec)
        base = char_format(spec.kind, spec.level)
        cursor.setBlockCharFormat(base)
        if spec.runs is not None:
            for r in merge_runs(spec.runs) or []:
                cursor.insertText(r.text.replace("\n", LINE_SEP), char_format(spec.kind, spec.level, r))
        elif spec.text:
            cursor.insertText(spec.text.replace("\n", LINE_SEP), base)
        cursor.setCharFormat(base)
        prev = spec
    doc.setModified(False)
    doc.setUndoRedoEnabled(True)


# ------------------------------------------------------------------ doc -> model
def _runs_of(block, kind: str) -> list[Run]:
    runs: list[Run] = []
    it = block.begin()
    while not it.atEnd():
        frag = it.fragment()
        it += 1
        if not frag.isValid():
            continue
        fmt = frag.charFormat()
        text = frag.text().replace(LINE_SEP, "\n")
        if not text:
            continue
        bold = fmt.fontWeight() >= 600 and kind != "heading"
        italic = fmt.fontItalic() and kind != "quote"
        link = fmt.anchorHref() if fmt.isAnchor() and fmt.anchorHref() else None
        underline = fmt.fontUnderline() and not link
        code = bool(fmt.property(P_CODE))
        va = fmt.verticalAlignment()
        runs.append(Run(text, bold, italic, underline, code, link,
                        va == QTextCharFormat.AlignSuperScript, va == QTextCharFormat.AlignSubScript,
                        fmt.fontStrikeOut()))
    return merge_runs(runs)


def _plain(block) -> str:
    return block.text().replace(LINE_SEP, "\n")


def _prop(bf: QTextBlockFormat, pid: int, default: Any) -> Any:
    v = bf.property(pid)
    return default if v is None or v == "" or v == "[]" or v == [] else v


def blocks_from_document(doc: QTextDocument, originals: dict[str, Block]) -> list[Block]:
    specs: list[dict[str, Any]] = []
    blk = doc.begin()
    while blk.isValid():
        bf = blk.blockFormat()
        kind = str(_prop(bf, P_KIND, "paragraph"))
        d = {"kind": kind, "id": str(_prop(bf, P_ID, "")) or new_id(),
             "level": int(_prop(bf, P_LEVEL, 1)), "kwn": bool(_prop(bf, P_KWN, False)),
             "style": str(_prop(bf, P_STYLE, "")) or None, "text": _plain(blk),
             "align": str(_prop(bf, P_ALIGN, "")),
             "runs": None if kind in ("code", "poetry", "poem_title", "scene", "placeholder")
             else _runs_of(blk, kind)}
        raw = _prop(bf, P_DATA, "")
        d["data"] = json.loads(raw) if raw else {}
        specs.append(d)
        blk = blk.next()

    out: list[Block] = []
    used: set[str] = set()

    def fresh(sid: str) -> str:
        if sid in used or not sid:
            sid = new_id()
        used.add(sid)
        return sid

    def orig(sid: str, cls):
        o = originals.get(sid)
        return o if isinstance(o, cls) else None

    i = 0
    while i < len(specs):
        s = specs[i]
        kind = s["kind"]
        if kind in LIST_KINDS:
            ordered = kind == "list_number"
            items = [s["runs"] or []]
            j = i + 1
            while j < len(specs) and specs[j]["kind"] == kind:
                items.append(specs[j]["runs"] or [])
                j += 1
            o = orig(s["id"], ListBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, ordered=ordered, items=items) if o else \
                ListBlock(id=sid, ordered=ordered, items=items)
            nb.keep_with_next = s["kwn"]
            out.append(nb)
            i = j
            continue
        if kind == "quote":
            attr: list[Run] = []
            j = i + 1
            if j < len(specs) and specs[j]["kind"] == "quote_attr" and specs[j]["id"] == s["id"]:
                attr = specs[j]["runs"] or []
                j += 1
            o = orig(s["id"], QuoteBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, runs=s["runs"] or [], attribution=attr) if o else \
                QuoteBlock(id=sid, runs=s["runs"] or [], attribution=attr)
            nb.keep_with_next, nb.style = s["kwn"], s["style"]
            out.append(nb)
            i = j
            continue
        if kind == "quote_attr":  # orphaned attribution: keep the text as a quote
            out.append(QuoteBlock(id=fresh(new_id()), runs=s["runs"] or []))
            i += 1
            continue
        if kind == "poem_title":
            j = i + 1
            title = s["text"]
            if j < len(specs) and specs[j]["kind"] == "poetry" and specs[j]["id"] == s["id"]:
                p = specs[j]
                o = orig(p["id"], PoetryBlock)
                sid = fresh(p["id"])
                nb = replace(o, id=sid, title=title, text=p["text"]) if o else \
                    PoetryBlock(id=sid, title=title, text=p["text"])
                nb.keep_with_next, nb.style, nb.align = p["kwn"], p["style"], p["align"]
                out.append(nb)
                i = j + 1
            else:  # the poem body was deleted: keep the title as text rather than lose it
                out.append(ParagraphBlock(id=fresh(new_id()), runs=[Run(title, bold=True)]))
                i += 1
            continue
        if kind == "poetry":
            o = orig(s["id"], PoetryBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, title="", text=s["text"]) if o else PoetryBlock(id=sid, text=s["text"])
            nb.keep_with_next, nb.style, nb.align = s["kwn"], s["style"], s["align"]
            out.append(nb)
        elif kind == "heading":
            o = orig(s["id"], HeadingBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, level=s["level"], runs=s["runs"] or []) if o else \
                HeadingBlock(id=sid, level=s["level"], runs=s["runs"] or [])
            nb.keep_with_next, nb.style = s["kwn"], s["style"]
            out.append(nb)
        elif kind == "code":
            o = orig(s["id"], CodeBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, text=s["text"]) if o else CodeBlock(id=sid, text=s["text"])
            nb.keep_with_next, nb.style = s["kwn"], s["style"]
            out.append(nb)
        elif kind == "scene":
            o = orig(s["id"], SceneBreakBlock)
            sid = fresh(s["id"])
            glyph = s["text"].strip() or "* * *"
            out.append(replace(o, id=sid, glyph=glyph) if o else SceneBreakBlock(id=sid, glyph=glyph))
        elif kind == "exercise":
            o = orig(s["id"], ExerciseBlock)
            sid = fresh(s["id"])
            data = s["data"]
            nb = replace(o, id=sid, runs=s["runs"] or []) if o else ExerciseBlock(
                id=sid, kind=data.get("kind", "exercise"), title=data.get("title", ""),
                runs=s["runs"] or [])
            nb.keep_with_next, nb.style = s["kwn"], s["style"]
            out.append(nb)
        elif kind == "footnote":
            o = orig(s["id"], FootnoteBlock)
            sid = fresh(s["id"])
            out.append(replace(o, id=sid, runs=s["runs"] or []) if o else FootnoteBlock(
                id=sid, label=s["data"].get("label", ""), runs=s["runs"] or []))
        elif kind == "placeholder":
            o = originals.get(s["id"])
            if o is not None and s["id"] not in used:
                used.add(s["id"])
                out.append(o)
            # a placeholder duplicated by splitting is dropped: it carries no text of its own
        else:  # paragraph
            o = orig(s["id"], ParagraphBlock)
            sid = fresh(s["id"])
            nb = replace(o, id=sid, runs=s["runs"] or []) if o else \
                ParagraphBlock(id=sid, runs=s["runs"] or [])
            nb.keep_with_next, nb.style, nb.align = s["kwn"], s["style"], s["align"]
            out.append(nb)
        i += 1
    return out
