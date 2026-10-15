"""Page geometry and book-level layout settings (presentation, not content)."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

from .content_blocks import new_id

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
class CoverLayer:
    """One element of a cover: text, image, shape, line, frame or generated pattern.

    Geometry is stored as fractions of the page so the design survives page-size changes.
    Text may contain {title} {subtitle} {author} {publisher} tokens, resolved at render time.
    """
    kind: str = "text"  # text | image | rect | ellipse | line | frame | pattern
    id: str = field(default_factory=new_id)
    name: str = ""
    role: str = ""  # title | subtitle | author | publisher | accent | deco | photo (palettes use roles)
    x: float = 0.1
    y: float = 0.1
    w: float = 0.8
    h: float = 0.2
    rotation: float = 0.0
    opacity: float = 1.0
    visible: bool = True
    locked: bool = False
    # shapes / frames / patterns
    fill: str | None = "#FFFFFF"
    fill2: str | None = None  # gradient end (vertical)
    stroke: str | None = None
    stroke_width: float = 1.0
    radius: float = 0.0  # corner radius in points
    pattern: str = "stripes"  # stripes | dots | grid | waves | circles | triangles
    scale: float = 18.0  # pattern cell size in points
    # text
    text: str = ""
    font_family: str = "serif"
    size: float = 24.0
    bold: bool = False
    italic: bool = False
    color: str = "#FFFFFF"
    align: str = "center"
    line_height: float = 1.15
    uppercase: bool = False
    autofit: bool = False  # shrink the text until it fits the box
    valign: str = "top"  # top | middle | bottom
    shadow: bool = False
    shadow_color: str = "#000000"
    # image
    asset: str = ""
    fit: str = "cover"  # cover (centre-cropped) | contain
    flip: bool = False
    fx: dict = field(default_factory=dict)  # grayscale, sepia, brightness, contrast, saturation, blur, tint, tint_alpha

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoverLayer":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


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
    # Layered design. When a side has no layers the simple fields above generate the cover.
    front_layers: list[CoverLayer] = field(default_factory=list)
    back_layers: list[CoverLayer] = field(default_factory=list)
    back_background: str | None = None  # None -> same as the front
    spine_color: str | None = None  # None -> same as the front background
    spine_text: bool = True  # title and author printed along the spine of a wrap-around cover
    preset: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            d[f.name] = [x.to_dict() for x in v] if f.name in ("front_layers", "back_layers") else v
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoverDesign":
        known = {f.name for f in fields(cls)}
        kw = {k: v for k, v in d.items() if k in known and k not in ("front_layers", "back_layers")}
        c = cls(**kw)
        c.front_layers = [CoverLayer.from_dict(x) for x in d.get("front_layers", [])]
        c.back_layers = [CoverLayer.from_dict(x) for x in d.get("back_layers", [])]
        return c


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
    chapter_number_style: str = "none"  # none | arabic | roman
    chapter_label: str = "Chapter {n}"  # printed above the title when numbering is on
    chapter_ornament: str = "none"  # none | rule | dots | stars | bullet | dash
    stanza_gap: float = 0.9  # blank-line height in poems, as a multiple of the line height
    poems_new_page: bool = False  # every poem starts on a new page
    # Front matter
    show_toc: bool = True
    toc_depth: int = 2
    toc_page_numbers: bool = True
    poem_index: str = "none"  # none | titles | first_lines: list of poems in the contents page
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
