"""Book statistics for the statistics dialog."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.content_blocks import LayoutBlock
from ..domain.book import BookProject
from ..domain.content_blocks import (CodeBlock, HeadingBlock, ImageBlock, ListBlock, ParagraphBlock,
                                     PoetryBlock, TableBlock)
from ..domain.sections import GENERATED_KINDS
from ..layout.model import LayoutResult

WORDS_PER_MINUTE = 230  # silent reading speed used for the estimate (poetry reads slower; not adjusted)


@dataclass
class ChapterStat:
    title: str
    words: int
    pages: int | None = None


@dataclass
class BookStats:
    words: int = 0
    characters: int = 0
    characters_no_spaces: int = 0
    paragraphs: int = 0
    poems: int = 0
    verse_lines: int = 0
    longest_poem_lines: int = 0
    headings: int = 0
    images: int = 0
    tables: int = 0
    code_blocks: int = 0
    list_items: int = 0
    sections: int = 0
    chapters: int = 0
    hidden_sections: int = 0
    pages: int | None = None
    blank_pages: int | None = None
    reading_minutes: int = 0
    chapter_stats: list[ChapterStat] = field(default_factory=list)

    @property
    def avg_words_per_chapter(self) -> int:
        return self.words // self.chapters if self.chapters else 0

    def rows(self) -> list[tuple[str, str]]:
        r = [("Words", f"{self.words:,}"), ("Characters (with spaces)", f"{self.characters:,}"),
             ("Characters (without spaces)", f"{self.characters_no_spaces:,}"),
             ("Estimated reading time", _fmt_minutes(self.reading_minutes)),
             ("Chapters", f"{self.chapters}"), ("Sections (all levels)", f"{self.sections}"),
             ("Hidden sections", f"{self.hidden_sections}"),
             ("Average words per chapter", f"{self.avg_words_per_chapter:,}"),
             ("Paragraphs", f"{self.paragraphs:,}"), ("Headings", f"{self.headings}"),
             ("Poems", f"{self.poems}"), ("Lines of verse", f"{self.verse_lines:,}"),
             ("Longest poem (lines)", f"{self.longest_poem_lines}"), ("List items", f"{self.list_items}"),
             ("Images", f"{self.images}"), ("Tables", f"{self.tables}"), ("Code blocks", f"{self.code_blocks}")]
        if self.pages is not None:
            r.insert(4, ("Pages (current layout)", f"{self.pages}"))
            r.insert(5, ("Blank pages", f"{self.blank_pages}"))
        return r


def _fmt_minutes(m: int) -> str:
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


def compute_stats(book: BookProject, layout: LayoutResult | None = None) -> BookStats:
    st = BookStats()
    for s in book.walk():
        st.sections += 1
        if not s.enabled:
            st.hidden_sections += 1
            continue
        words = 0
        for b in s.blocks:
            text = b.plain_text()
            words += len(text.split())
            st.characters += len(text)
            st.characters_no_spaces += sum(1 for c in text if not c.isspace())
            if isinstance(b, ParagraphBlock) and b.runs:
                st.paragraphs += 1
            elif isinstance(b, HeadingBlock):
                st.headings += 1
            elif isinstance(b, PoetryBlock):
                n = sum(1 for l in b.text.splitlines() if l.strip())
                st.poems += 1
                st.verse_lines += n
                st.longest_poem_lines = max(st.longest_poem_lines, n)
            elif isinstance(b, (ImageBlock, LayoutBlock)):
                st.images += 1 if not isinstance(b, LayoutBlock) or b.asset else 0
            elif isinstance(b, TableBlock):
                st.tables += 1
            elif isinstance(b, CodeBlock):
                st.code_blocks += 1
            elif isinstance(b, ListBlock):
                st.list_items += len(b.items)
        st.words += words
        if s.kind == "chapter":
            st.chapters += 1
        if s.kind not in GENERATED_KINDS and words:
            pages = None
            if layout is not None and s.id in layout.section_pages:
                start = layout.section_pages[s.id]
                later = [p for sid, p in layout.section_pages.items() if p > start]
                pages = (min(later) if later else layout.page_count) - start
            st.chapter_stats.append(ChapterStat(s.title or s.kind, words, pages))
    st.reading_minutes = round(st.words / WORDS_PER_MINUTE)
    if layout is not None:
        st.pages = layout.page_count
        st.blank_pages = sum(1 for p in layout.pages if p.blank)
    st.chapter_stats.sort(key=lambda c: -c.words)
    return st
