"""Hierarchical book structure: front matter, parts, chapters, back matter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content_blocks import Block, new_id

FRONT_KINDS = ["front_cover", "title_page", "copyright", "dedication", "foreword",
               "preface", "toc"]
MAIN_KINDS = ["part", "chapter", "section"]
BACK_KINDS = ["appendix", "glossary", "bibliography", "index", "acknowledgments",
              "back_matter", "back_cover"]
ALL_KINDS = FRONT_KINDS + MAIN_KINDS + BACK_KINDS

KIND_LABELS = {
    "front_cover": "Front cover", "title_page": "Title page", "copyright": "Copyright page",
    "dedication": "Dedication", "foreword": "Foreword", "preface": "Preface",
    "toc": "Table of contents", "part": "Part", "chapter": "Chapter", "section": "Section",
    "appendix": "Appendix", "glossary": "Glossary", "bibliography": "Bibliography",
    "index": "Index", "acknowledgments": "Acknowledgments", "back_matter": "Back matter",
    "back_cover": "Back cover",
}

# Kinds whose content is generated from metadata/headings when they have no blocks.
GENERATED_KINDS = {"front_cover", "title_page", "copyright", "toc", "back_cover"}
# Kinds that begin on a right-hand page in facing-page books.
RECTO_KINDS = {"title_page", "dedication", "foreword", "preface", "toc", "part"}
NUMBERING_OFF_KINDS = {"front_cover", "back_cover"}


def matter_of(kind: str) -> str:
    if kind in FRONT_KINDS:
        return "front"
    if kind in BACK_KINDS:
        return "back"
    return "main"


@dataclass
class Section:
    title: str = ""
    kind: str = "chapter"
    id: str = field(default_factory=new_id)
    blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)
    enabled: bool = True  # optional sections can be disabled without deleting them
    in_toc: bool = True
    new_page: bool | None = None  # None -> follow book settings
    show_title: bool = True
    # Page setup override for this section (and its sub-sections): "columns", "column_gap_mm",
    # "margins" {top,bottom,inner,outer} in mm, "page_size" or "width_mm"/"height_mm". Empty = book settings.
    page: dict[str, Any] = field(default_factory=dict)

    @property
    def matter(self) -> str:
        return matter_of(self.kind)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id, "title": self.title, "kind": self.kind,
            "enabled": self.enabled, "in_toc": self.in_toc, "new_page": self.new_page,
            "show_title": self.show_title,
            "blocks": [b.to_dict() for b in self.blocks],
            "children": [c.to_dict() for c in self.children],
        }
        if self.page:
            d["page"] = dict(self.page)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return cls(
            id=d.get("id") or new_id(), title=d.get("title", ""), kind=d.get("kind", "chapter"),
            enabled=d.get("enabled", True), in_toc=d.get("in_toc", True),
            new_page=d.get("new_page"), show_title=d.get("show_title", True),
            page=dict(d.get("page") or {}),
            blocks=[Block.from_dict(b) for b in d.get("blocks", [])],
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )

    def clone(self) -> "Section":
        """Deep copy with fresh stable identifiers."""
        c = Section.from_dict(self.to_dict())
        for s in c.walk():
            s.id = new_id()
            for b in s.blocks:
                b.id = new_id()
        return c
