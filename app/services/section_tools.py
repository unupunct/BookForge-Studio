"""Reorganising imported text: split a long section into many, merge neighbours."""
from __future__ import annotations

from ..domain.book import BookProject
from ..domain.content_blocks import Block, HeadingBlock, PoetryBlock, runs_text
from ..domain.sections import Section


class SectionToolError(Exception):
    pass


def _siblings(book: BookProject, section_id: str) -> tuple[list[Section], int]:
    loc = book.find_parent(section_id)
    if loc is None:
        raise SectionToolError("Section not found")
    return loc


def poem_label(p: PoetryBlock, limit: int = 48) -> str:
    first = next((l.strip() for l in p.text.splitlines() if l.strip()), "")
    title = p.title.strip()
    if title and not (len(title) <= 4 and title.replace(".", "").isdigit()):
        return title[:limit]
    label = (f"{title}. {first}" if title else first) or "Untitled poem"
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def _commit(book: BookProject, section: Section, groups: list[tuple[str, list[Block]]],
            head: list[Block]) -> list[Section]:
    siblings, idx = _siblings(book, section.id)
    new = [Section(title, section.kind, blocks=blocks, in_toc=section.in_toc, show_title=True,
                   new_page=section.new_page) for title, blocks in groups]
    section.blocks = head
    pos = idx + 1
    for s in new:
        siblings.insert(pos, s)
        pos += 1
    if not section.blocks and not section.children and new:
        siblings.remove(section)  # nothing is left in the original
    return new


def split_by_poems(book: BookProject, section_id: str) -> list[Section]:
    """Every poem becomes its own section, named after the poem (title, else first line).

    Blocks after a poem (until the next poem) stay with it. Text before the first poem stays in the
    original section. The poem's own title is dropped from the block when it became the section title,
    so it is not printed twice.
    """
    sec = book.find_section(section_id)
    if sec is None:
        raise SectionToolError("Section not found")
    head: list[Block] = []
    groups: list[tuple[str, list[Block]]] = []
    for b in sec.blocks:
        if isinstance(b, PoetryBlock):
            label = poem_label(b)
            numeric = b.title.strip() and len(b.title.strip()) <= 4 and b.title.strip().replace(".", "").isdigit()
            if b.title.strip() and not numeric:
                b.title = ""  # the section title now shows it
            groups.append((label, [b]))
        elif groups:
            groups[-1][1].append(b)
        else:
            head.append(b)
    if not groups:
        raise SectionToolError("This section contains no poems")
    return _commit(book, sec, groups, head)


def split_by_headings(book: BookProject, section_id: str, level: int = 1) -> list[Section]:
    """Headings of `level` start new sections (the heading text becomes the section title)."""
    sec = book.find_section(section_id)
    if sec is None:
        raise SectionToolError("Section not found")
    head: list[Block] = []
    groups: list[tuple[str, list[Block]]] = []
    for b in sec.blocks:
        if isinstance(b, HeadingBlock) and b.level == level:
            groups.append((runs_text(b.runs).strip() or "Untitled", []))
            continue
        if isinstance(b, HeadingBlock) and b.level > level and groups:
            b.level -= level
        (groups[-1][1] if groups else head).append(b)
    if not groups:
        raise SectionToolError(f"This section has no Heading {level} to split at")
    return _commit(book, sec, groups, head)


def merge_with_next(book: BookProject, section_id: str) -> Section:
    """Append the next sibling (its text and sub-sections) to this section."""
    siblings, idx = _siblings(book, section_id)
    if idx + 1 >= len(siblings):
        raise SectionToolError("There is no next section to merge")
    a, b = siblings[idx], siblings[idx + 1]
    if b.title.strip() and b.show_title and a.kind == b.kind:
        from ..domain.content_blocks import HeadingBlock as H, Run
        a.blocks.append(H(level=1, runs=[Run(b.title)]))  # keep the merged section's title as a heading
    a.blocks.extend(b.blocks)
    a.children.extend(b.children)
    siblings.pop(idx + 1)
    return a
