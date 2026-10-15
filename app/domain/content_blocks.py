"""Semantic content blocks. Independent of PySide6 and ReportLab.

Blocks describe *what* the content is (heading level, poem, recipe...), never
how it looks. Presentation is resolved later through named styles.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Run:
    """An inline span of text with semantic formatting flags."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    code: bool = False
    link: str | None = None
    sup: bool = False
    sub: bool = False
    strike: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text}
        for k in ("bold", "italic", "underline", "code", "sup", "sub", "strike"):
            if getattr(self, k):
                d[k] = True
        if self.link:
            d["link"] = self.link
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Run":
        return cls(
            text=str(d.get("text", "")),
            bold=bool(d.get("bold", False)),
            italic=bool(d.get("italic", False)),
            underline=bool(d.get("underline", False)),
            code=bool(d.get("code", False)),
            link=d.get("link"),
            sup=bool(d.get("sup", False)),
            sub=bool(d.get("sub", False)),
            strike=bool(d.get("strike", False)),
        )

    def same_format(self, other: "Run") -> bool:
        return self.fmt() == other.fmt()

    def fmt(self) -> tuple:
        return (self.bold, self.italic, self.underline, self.code, self.link,
                self.sup, self.sub, self.strike)


def runs_text(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


def merge_runs(runs: list[Run]) -> list[Run]:
    out: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if out and out[-1].same_format(r):
            out[-1] = Run(out[-1].text + r.text, *r.fmt())
        else:
            out.append(Run(r.text, *r.fmt()))
    return out


def plain_runs(text: str) -> list[Run]:
    return [Run(text)] if text else []


# Field names holding structured inline content, used by (de)serialisation.
_RUN_LIST_FIELDS = {"runs", "caption", "attribution"}
_RUN_LISTS_FIELDS = {"items"}

BLOCK_TYPES: dict[str, type["Block"]] = {}


@dataclass
class Block:
    type: ClassVar[str] = "block"
    id: str = field(default_factory=new_id)
    style: str | None = None  # optional named-style override
    keep_with_next: bool = False
    locked: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        BLOCK_TYPES[cls.type] = cls

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name in _RUN_LIST_FIELDS and v is not None:
                v = [r.to_dict() for r in v]
            elif f.name in _RUN_LISTS_FIELDS:
                v = [[r.to_dict() for r in item] for item in v]
            d[f.name] = v
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Block":
        t = d.get("type")
        klass = BLOCK_TYPES.get(str(t))
        if klass is None:
            # Unknown block types are preserved as paragraphs so nothing is lost.
            return ParagraphBlock(runs=[Run(f"[Unsupported block type '{t}': {d.get('text', '')}]")])
        kwargs: dict[str, Any] = {}
        known = {f.name for f in fields(klass)}
        for k, v in d.items():
            if k == "type" or k not in known:
                continue
            if k in _RUN_LIST_FIELDS and v is not None:
                v = [Run.from_dict(r) for r in v]
            elif k in _RUN_LISTS_FIELDS:
                v = [[Run.from_dict(r) for r in item] for item in v]
            kwargs[k] = v
        return klass(**kwargs)

    # -- helpers -----------------------------------------------------------
    def plain_text(self) -> str:
        return ""


@dataclass
class ParagraphBlock(Block):
    type: ClassVar[str] = "paragraph"
    runs: list[Run] = field(default_factory=list)
    # Per-paragraph formatting kept from imported documents (None/"" = follow the style)
    align: str = ""
    left_indent: float | None = None
    first_indent: float | None = None
    space_before: float | None = None
    space_after: float | None = None

    def plain_text(self) -> str:
        return runs_text(self.runs)


@dataclass
class HeadingBlock(Block):
    type: ClassVar[str] = "heading"
    level: int = 1
    runs: list[Run] = field(default_factory=list)
    in_toc: bool = True

    def plain_text(self) -> str:
        return runs_text(self.runs)


@dataclass
class ListBlock(Block):
    type: ClassVar[str] = "list"
    ordered: bool = False
    items: list[list[Run]] = field(default_factory=list)

    def plain_text(self) -> str:
        return "\n".join(runs_text(i) for i in self.items)


@dataclass
class ImageBlock(Block):
    type: ClassVar[str] = "image"
    asset: str = ""  # asset id in BookProject.assets
    width_pct: float = 100.0  # percentage of text width
    align: str = "center"
    alt: str = ""
    caption: list[Run] = field(default_factory=list)
    own_page: bool = False  # place on a dedicated page
    crop: list[float] | None = None  # [left, top, right, bottom] fractions

    def plain_text(self) -> str:
        return runs_text(self.caption)


@dataclass
class TableBlock(Block):
    type: ClassVar[str] = "table"
    rows: list[list[str]] = field(default_factory=list)
    header_rows: int = 1
    col_widths: list[float] | None = None  # relative weights
    caption: list[Run] = field(default_factory=list)
    align: list[str] | None = None  # per column: left|center|right
    split_rows: bool = False  # allow a row to be split across pages (unsupported: warn)

    def plain_text(self) -> str:
        return "\n".join("\t".join(r) for r in self.rows) + "\n" + runs_text(self.caption)


@dataclass
class CodeBlock(Block):
    type: ClassVar[str] = "code"
    text: str = ""
    language: str = ""
    caption: list[Run] = field(default_factory=list)

    def plain_text(self) -> str:
        return self.text


@dataclass
class QuoteBlock(Block):
    type: ClassVar[str] = "quote"
    runs: list[Run] = field(default_factory=list)
    attribution: list[Run] = field(default_factory=list)

    def plain_text(self) -> str:
        return runs_text(self.runs) + " " + runs_text(self.attribution)


@dataclass
class PoetryBlock(Block):
    type: ClassVar[str] = "poetry"
    text: str = ""  # lines separated by \n, stanzas by an empty line
    title: str = ""
    one_per_page: bool = False
    continuation_marker: bool = True  # print "(continued)" when a poem spans pages
    align: str = ""  # "" = follow the poetry style (template); left | center | right

    def plain_text(self) -> str:
        return (self.title + "\n" if self.title else "") + self.text


@dataclass
class SceneBreakBlock(Block):
    type: ClassVar[str] = "scene_break"
    glyph: str = "* * *"


@dataclass
class PageBreakBlock(Block):
    type: ClassVar[str] = "page_break"
    blank: bool = False  # intentional blank page
    recto: bool = False  # continue on the next right-hand page


@dataclass
class RecipeBlock(Block):
    type: ClassVar[str] = "recipe"
    title: str = ""
    description: str = ""
    prep_time: str = ""
    cook_time: str = ""
    servings: str = ""
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    notes: str = ""
    nutrition: str = ""  # user-supplied only; never generated
    image: str = ""

    def plain_text(self) -> str:
        return "\n".join([self.title, self.description, *self.ingredients,
                          *self.instructions, self.notes, self.nutrition])


EXERCISE_KINDS = ("objective", "definition", "example", "exercise", "question",
                  "answer", "note", "warning", "reference")


@dataclass
class ExerciseBlock(Block):
    type: ClassVar[str] = "exercise"
    kind: str = "exercise"
    title: str = ""
    runs: list[Run] = field(default_factory=list)

    def plain_text(self) -> str:
        return self.title + " " + runs_text(self.runs)


@dataclass
class FootnoteBlock(Block):
    """A footnote definition rendered at the end of its section (endnote style)."""

    type: ClassVar[str] = "footnote"
    label: str = ""
    runs: list[Run] = field(default_factory=list)

    def plain_text(self) -> str:
        return self.label + " " + runs_text(self.runs)


def block_text_fields(block: Block) -> list[tuple[str, str]]:
    """Searchable (field name, text) pairs for a block."""
    out: list[tuple[str, str]] = []
    if isinstance(block, (ParagraphBlock, HeadingBlock, QuoteBlock, ExerciseBlock, FootnoteBlock)):
        out.append(("runs", runs_text(block.runs)))
    elif isinstance(block, ListBlock):
        out.extend((f"items[{i}]", runs_text(it)) for i, it in enumerate(block.items))
    elif isinstance(block, CodeBlock):
        out.append(("text", block.text))
    elif isinstance(block, PoetryBlock):
        out.append(("text", block.text))
    elif isinstance(block, TableBlock):
        out.extend((f"cell[{r}][{c}]", t) for r, row in enumerate(block.rows)
                   for c, t in enumerate(row))
    if hasattr(block, "caption") and block.caption:
        out.append(("caption", runs_text(block.caption)))
    return out
