"""Page geometry and book-level layout settings (presentation, not content)."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

MM_TO_PT = 72.0 / 25.4
IN_TO_PT = 72.0

# name -> (width_mm, height_mm)
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "US Letter": (215.9, 279.4),
    "US Trade 6x9": (152.4, 228.6),
    "Custom": (152.4, 228.6),
}


@dataclass
class Margins:
    top: float = 20.0  # millimetres
    bottom: float = 22.0
    inner: float = 22.0
    outer: float = 16.0

    def to_dict(self) -> dict[str, float]:
        return {"top": self.top, "bottom": self.bottom, "inner": self.inner, "outer": self.outer}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Margins":
        known = {f.name for f in fields(cls)}
        return cls(**{k: float(v) for k, v in d.items() if k in known})


@dataclass
class CoverDesign:
    enabled: bool = True
    background: str = "#2B2B2B"
    background2: str | None = None  # gradient end colour (vertical), optional
    title_color: str = "#F2F2F2"
    author_color: str = "#D9A066"
    font_family: str = "serif"
    image_asset: str = ""
    image_mode: str = "behind"  # behind | top
    title_size: float = 36.0
    subtitle_size: float = 16.0
    author_size: float = 16.0
    back_text: str = ""
    publisher_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoverDesign":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class BookSettings:
    template: str = "general_purpose"
    page_size: str = "A5"
    width_mm: float = 148.0
    height_mm: float = 210.0
    landscape: bool = False
    margins: Margins = field(default_factory=Margins)
    mirrored_margins: bool = True  # facing pages: inner/outer instead of left/right
    facing_pages: bool = True
    # Per-matter margin overrides: {"front": {"top": 25, ...}, "back": {...}}
    matter_margins: dict[str, dict[str, float]] = field(default_factory=dict)
    # Typography defaults
    body_font: str = "serif"
    body_size: float = 11.0
    line_height: float = 1.4
    paragraph_spacing: float = 0.0
    first_line_indent: float = 14.0
    justify: bool = True
    widow_lines: int = 2
    orphan_lines: int = 2
    # Chapter and section opening rules
    chapter_new_page: bool = True
    chapter_right_page: bool = False
    chapter_drop: float = 60.0  # points of drop at chapter opening
    # Front matter
    show_toc: bool = True
    toc_depth: int = 2
    toc_page_numbers: bool = True
    list_of_figures: bool = False
    list_of_tables: bool = False
    # Numbering and running elements
    front_numbering: str = "roman"  # roman | arabic | none
    header_verso: str = "{title}"
    header_recto: str = "{chapter}"
    footer: str = "{page}"
    footer_position: str = "center"  # center | outer | none
    header_rule: bool = True
    # Image defaults
    image_default_width_pct: float = 80.0
    # Print
    gutter_mm: float = 0.0
    bleed_mm: float = 3.0
    export_profile: str = "digital"
    paper_thickness_mm: float = 0.1  # user/printer supplied; never a universal constant
    cover: CoverDesign = field(default_factory=CoverDesign)

    def page_size_pt(self) -> tuple[float, float]:
        w, h = self.width_mm * MM_TO_PT, self.height_mm * MM_TO_PT
        if self.landscape and h > w:
            w, h = h, w
        elif not self.landscape and w > h and self.page_size != "Custom":
            w, h = h, w
        return w, h

    def margins_for(self, matter: str) -> Margins:
        m = Margins(**self.margins.to_dict())
        for k, v in self.matter_margins.get(matter, {}).items():
            if hasattr(m, k):
                setattr(m, k, float(v))
        return m

    def set_page_size(self, name: str) -> None:
        self.page_size = name
        if name in PAGE_SIZES and name != "Custom":
            self.width_mm, self.height_mm = PAGE_SIZES[name]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            d[f.name] = v.to_dict() if hasattr(v, "to_dict") else v
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BookSettings":
        s = cls()
        known = {f.name for f in fields(cls)}
        for k, v in d.items():
            if k not in known:
                continue
            if k == "margins":
                v = Margins.from_dict(v)
            elif k == "cover":
                v = CoverDesign.from_dict(v)
            setattr(s, k, v)
        return s
