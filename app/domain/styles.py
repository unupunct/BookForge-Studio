"""Named style definitions with inheritance and template overrides."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any


@dataclass
class StyleDefinition:
    name: str
    based_on: str | None = None
    # Every presentation property is optional so that inheritance can resolve it.
    font_family: str | None = None
    font_size: float | None = None  # points
    bold: bool | None = None
    italic: bool | None = None
    color: str | None = None  # #RRGGBB
    space_before: float | None = None  # points
    space_after: float | None = None
    line_height: float | None = None  # multiple of font size
    align: str | None = None  # left | right | center | justify
    first_indent: float | None = None
    left_indent: float | None = None
    right_indent: float | None = None
    keep_with_next: bool | None = None
    page_break_before: bool | None = None
    background: str | None = None
    border: bool | None = None
    user_modified: bool = False  # protects the style from template re-application

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)
                if getattr(self, f.name) is not None and f.name != "name"} | {"name": self.name}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StyleDefinition":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class ResolvedStyle:
    name: str
    font_family: str = "serif"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    space_before: float = 0.0
    space_after: float = 0.0
    line_height: float = 1.35
    align: str = "left"
    first_indent: float = 0.0
    left_indent: float = 0.0
    right_indent: float = 0.0
    keep_with_next: bool = False
    page_break_before: bool = False
    background: str | None = None
    border: bool = False


_PROPS = [f.name for f in fields(ResolvedStyle) if f.name != "name"]


def default_styles() -> dict[str, StyleDefinition]:
    S = StyleDefinition
    styles = [
        S("body", font_family="serif", font_size=11, line_height=1.4, align="justify",
          space_after=0, first_indent=14, color="#000000"),
        S("first_paragraph", based_on="body", first_indent=0),
        S("book_title", based_on="body", font_family="serif", font_size=34, bold=True,
          align="center", first_indent=0, line_height=1.15, space_after=14),
        S("subtitle", based_on="book_title", font_size=18, bold=False, italic=True),
        S("author", based_on="book_title", font_size=16, bold=False),
        S("part_title", based_on="body", font_size=26, bold=True, align="center",
          first_indent=0, line_height=1.2, space_before=120, space_after=24,
          page_break_before=True),
        S("chapter_title", based_on="body", font_size=22, bold=True, align="left",
          first_indent=0, line_height=1.2, space_before=60, space_after=28,
          keep_with_next=True),
        S("heading1", based_on="body", font_size=17, bold=True, align="left", first_indent=0,
          line_height=1.25, space_before=20, space_after=8, keep_with_next=True),
        S("heading2", based_on="heading1", font_size=14, space_before=16, space_after=6),
        S("heading3", based_on="heading1", font_size=12, italic=True, space_before=12,
          space_after=4),
        S("heading4", based_on="heading3", font_size=11, italic=False),
        S("block_quote", based_on="body", italic=True, left_indent=28, right_indent=28,
          first_indent=0, space_before=8, space_after=8, align="left"),
        S("caption", based_on="body", font_size=9, italic=True, align="center",
          first_indent=0, line_height=1.25, space_before=4, space_after=10),
        S("footnote", based_on="body", font_size=8.5, first_indent=0, line_height=1.25,
          space_after=2),
        S("code", based_on="body", font_family="mono", font_size=8.5, align="left",
          first_indent=0, line_height=1.3, space_before=6, space_after=8,
          background="#F3F3F3", left_indent=6),
        S("poetry", based_on="body", font_size=11, italic=False, align="left",
          first_indent=0, line_height=1.5, left_indent=36),
        S("poetry_title", based_on="poetry", bold=True, left_indent=36, space_after=10),
        S("recipe_heading", based_on="heading1", font_size=18, space_before=0),
        S("table", based_on="body", font_size=9.5, align="left", first_indent=0,
          line_height=1.25),
        S("table_header", based_on="table", bold=True, background="#E8E8E8"),
        S("bibliography_entry", based_on="body", first_indent=-18, left_indent=18,
          align="left", space_after=4),
        S("toc_entry", based_on="body", first_indent=0, align="left", space_after=3),
        S("toc_title", based_on="chapter_title"),
        S("scene_break", based_on="body", align="center", first_indent=0, space_before=10,
          space_after=10),
        S("header_footer", based_on="body", font_size=9, first_indent=0, align="center",
          color="#555555", line_height=1.2),
        S("callout", based_on="body", font_size=10, align="left", first_indent=0,
          left_indent=8, space_before=6, space_after=6, background="#F6F1E7", border=True),
    ]
    return {s.name: s for s in styles}


class StyleSet:
    """Resolves inheritance chains. Changing a definition affects all users."""

    def __init__(self, defs: dict[str, StyleDefinition]):
        self.defs = defs

    def resolve(self, name: str) -> ResolvedStyle:
        chain: list[StyleDefinition] = []
        seen: set[str] = set()
        cur: str | None = name
        while cur and cur in self.defs and cur not in seen:
            seen.add(cur)
            chain.append(self.defs[cur])
            cur = self.defs[cur].based_on
        out = ResolvedStyle(name=name)
        for d in reversed(chain):  # base first, derived last
            for p in _PROPS:
                v = getattr(d, p)
                if v is not None:
                    setattr(out, p, v)
        return out


def merge_template_styles(current: dict[str, StyleDefinition],
                          template: dict[str, dict[str, Any]],
                          preserve_user_modified: bool = True) -> dict[str, StyleDefinition]:
    """Apply a template's style overrides without clobbering user customisations."""
    result = dict(current)
    for name, props in template.items():
        existing = result.get(name)
        if existing and existing.user_modified and preserve_user_modified:
            continue
        base = existing or StyleDefinition(name)
        merged = replace(base)
        for k, v in props.items():
            if k in {f.name for f in fields(StyleDefinition)} and k not in ("name", "user_modified"):
                setattr(merged, k, v)
        merged.user_modified = False
        result[name] = merged
    return result
