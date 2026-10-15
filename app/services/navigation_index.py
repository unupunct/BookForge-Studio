"""Quick-jump index: pages, sections, headings, poems and recipes, searched as you type."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from ..domain.book import BookProject
from ..domain.content_blocks import HeadingBlock, PoetryBlock, RecipeBlock, runs_text
from ..layout.model import LayoutResult
from .section_tools import poem_label


@dataclass
class NavEntry:
    kind: str  # page | section | heading | poem | recipe
    title: str
    section_id: str | None = None
    block_id: str | None = None
    page_index: int | None = None
    detail: str = ""


def fold(text: str) -> str:
    """Lower-case and strip diacritics so 'Marea' finds 'mărea' and 'ț' matches 't'."""
    d = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in d if not unicodedata.combining(c))


def build_index(book: BookProject, layout: LayoutResult | None = None) -> list[NavEntry]:
    out: list[NavEntry] = []

    def page_of(block_id: str | None = None, section_id: str | None = None) -> int | None:
        if layout is None:
            return None
        if block_id and block_id in layout.block_pages:
            return layout.block_pages[block_id][0]
        return layout.section_pages.get(section_id) if section_id else None

    for s in book.walk():
        if not s.enabled:
            continue
        if s.title.strip():
            out.append(NavEntry("section", s.title, s.id, None, page_of(section_id=s.id), s.kind.replace("_", " ")))
        for b in s.blocks:
            if isinstance(b, HeadingBlock) and b.runs:
                out.append(NavEntry("heading", runs_text(b.runs), s.id, b.id, page_of(b.id), s.title))
            elif isinstance(b, PoetryBlock):
                out.append(NavEntry("poem", poem_label(b, 70), s.id, b.id, page_of(b.id), s.title))
            elif isinstance(b, RecipeBlock) and b.title:
                out.append(NavEntry("recipe", b.title, s.id, b.id, page_of(b.id), s.title))
    return out


def resolve_page(layout: LayoutResult | None, query: str) -> NavEntry | None:
    """A printed page label ('iv', '12') or, failing that, a physical page number."""
    q = query.strip().lower()
    if not q or layout is None or not layout.pages:
        return None
    for p in layout.pages:
        if p.label.lower() == q:
            return NavEntry("page", f"Page {p.label}", None, None, p.index, f"sheet {p.index + 1}")
    if q.isdigit() and 1 <= int(q) <= layout.page_count:
        p = layout.pages[int(q) - 1]
        return NavEntry("page", f"Sheet {q}" + (f" (page {p.label})" if p.label else ""), None, None, p.index)
    return None


def search_index(entries: list[NavEntry], query: str, limit: int = 200) -> list[NavEntry]:
    q = fold(query.strip())
    if not q:
        return entries[:limit]
    words = q.split()
    scored = []
    for e in entries:
        t = fold(e.title)
        if all(w in t for w in words):
            scored.append((0 if t.startswith(q) else 1, len(t), e))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [e for _, _, e in scored[:limit]]
