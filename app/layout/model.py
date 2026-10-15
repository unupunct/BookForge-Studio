"""Shared layout model: the single description of every page.

Both the on-screen preview and the PDF exporter render *this* structure, so page
geometry, line breaks, page numbers and content placement cannot diverge.
Coordinates are PDF points with the origin at the top-left of the page and y
growing downward. No dependency on PySide6 or ReportLab.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass
class Glyphs:
    """A run of text drawn on one baseline with one font."""
    x: float
    y: float  # baseline
    text: str
    font: str  # registered font key (see typography.FontManager)
    size: float
    color: str = "#000000"
    underline: bool = False
    link: str | None = None  # "#anchor" for internal, otherwise an external URL
    word_space: float = 0.0  # extra width added to every space (justification)
    width: float = 0.0
    block_id: str | None = None
    kind: str = "text"

    def moved(self, dx: float, dy: float) -> "Glyphs":
        return replace(self, x=self.x + dx, y=self.y + dy)


@dataclass
class RectItem:
    x: float
    y: float
    w: float
    h: float
    fill: str | None = None
    stroke: str | None = None
    stroke_width: float = 0.5
    block_id: str | None = None
    gradient_to: str | None = None  # vertical gradient end colour
    kind: str = "rect"

    def moved(self, dx: float, dy: float) -> "RectItem":
        return replace(self, x=self.x + dx, y=self.y + dy)


@dataclass
class LineItem:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float = 0.5
    color: str = "#000000"
    block_id: str | None = None
    kind: str = "line"

    def moved(self, dx: float, dy: float) -> "LineItem":
        return replace(self, x1=self.x1 + dx, x2=self.x2 + dx, y1=self.y1 + dy, y2=self.y2 + dy)


@dataclass
class ImageItem:
    x: float
    y: float
    w: float
    h: float
    asset_id: str
    crop: tuple[float, float, float, float] | None = None
    alt: str = ""
    block_id: str | None = None
    missing: bool = False
    kind: str = "image"

    def moved(self, dx: float, dy: float) -> "ImageItem":
        return replace(self, x=self.x + dx, y=self.y + dy)


Item = Glyphs | RectItem | LineItem | ImageItem


@dataclass
class LayoutIssue:
    severity: str  # error | warning | info
    code: str
    message: str
    page_index: int | None = None
    block_id: str | None = None
    section_id: str | None = None


@dataclass
class OutlineEntry:
    level: int
    title: str
    anchor: str
    page_index: int = 0


@dataclass
class Page:
    index: int
    width: float
    height: float
    side: str  # recto (right-hand) | verso (left-hand)
    content_box: tuple[float, float, float, float]  # x0, y0, x1, y1
    matter: str = "main"
    section_id: str | None = None
    chapter_title: str = ""
    items: list[Item] = field(default_factory=list)
    decorations: list[Item] = field(default_factory=list)  # headers/footers/diagnostics
    label: str = ""  # printed page number ("iv", "12") or ""
    blank: str | None = None  # "intentional" | None
    full_bleed: bool = False  # covers: no margins, no running elements
    opening: bool = False  # a chapter opens on this page
    used: bool = False  # received flowed content
    anchors: dict[str, float] = field(default_factory=dict)
    block_ids: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.items

    def all_items(self) -> list[Item]:
        return self.items + self.decorations


@dataclass
class LayoutResult:
    pages: list[Page]
    issues: list[LayoutIssue] = field(default_factory=list)
    outline: list[OutlineEntry] = field(default_factory=list)
    page_width: float = 0.0
    page_height: float = 0.0
    block_pages: dict[str, list[int]] = field(default_factory=dict)
    section_pages: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def issues_by_severity(self, severity: str) -> list[LayoutIssue]:
        return [i for i in self.issues if i.severity == severity]
