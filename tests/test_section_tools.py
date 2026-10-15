import pytest
from PySide6.QtWidgets import QMessageBox

from app.domain.book import BookProject
from app.domain.content_blocks import HeadingBlock, ParagraphBlock, PoetryBlock, Run
from app.domain.sections import Section
from app.layout.pagination import LayoutEngine
from app.services.section_tools import (SectionToolError, merge_with_next, poem_label, split_by_headings,
                                        split_by_poems)
from tests.test_ui import chapter, qapp, wait_until, window  # noqa: F401  (fixtures)


def poems_book():
    b = BookProject()
    b.sections = [Section("Front", "title_page"), Section("Poeme", "chapter", blocks=[
        ParagraphBlock(runs=[Run("intro")]),
        PoetryBlock(title="Seară", text="Cade lumina\nincet"),
        ParagraphBlock(runs=[Run("notă după poem")]),
        PoetryBlock(title="2", text="Al doilea poem\nvers"),
        PoetryBlock(title="", text="Fără titlu deloc, un prim vers foarte lung care trebuie scurtat frumos\nx"),
    ]), Section("Epilog", "chapter")]
    return b


def test_split_by_poems_names_sections_and_keeps_every_block():
    b = poems_book()
    sid = b.sections[1].id
    all_blocks = [x.id for x in b.sections[1].blocks]
    new = split_by_poems(b, sid)
    assert [s.title for s in new][:2] == ["Seară", "2. Al doilea poem"]
    long_title = new[2].title
    assert long_title.startswith("Fără titlu deloc") and long_title.endswith("…") and len(long_title) <= 48
    assert [s.title for s in b.sections] == ["Front", "Poeme", "Seară", "2. Al doilea poem", long_title, "Epilog"]
    assert [x.plain_text() for x in b.sections[1].blocks] == ["intro"]  # text before the first poem stays
    assert [type(x).__name__ for x in new[0].blocks] == ["PoetryBlock", "ParagraphBlock"]  # note stays with its poem
    assert new[0].blocks[0].title == ""  # title now printed as the section title, not twice
    assert new[1].blocks[0].title == "2"  # a bare number is kept as the poem's own number
    after = [x.id for s in b.sections for x in s.blocks]
    assert sorted(after) == sorted(all_blocks)  # nothing lost or duplicated


def test_original_section_removed_when_it_would_be_empty():
    b = BookProject()
    b.sections = [Section("P", "chapter", blocks=[PoetryBlock(title="A", text="x\ny"), PoetryBlock(title="B", text="z\nw")])]
    new = split_by_poems(b, b.sections[0].id)
    assert [s.title for s in b.sections] == ["A", "B"] and len(new) == 2
    b.sections[0].blocks = [ParagraphBlock(runs=[Run("only prose")])]
    with pytest.raises(SectionToolError, match="no poems"):
        split_by_poems(b, b.sections[0].id)


def test_split_by_headings_and_merge_roundtrip():
    b = BookProject()
    b.sections = [Section("Tot", "chapter", blocks=[
        ParagraphBlock(runs=[Run("p0")]), HeadingBlock(level=1, runs=[Run("Unu")]), ParagraphBlock(runs=[Run("p1")]),
        HeadingBlock(level=2, runs=[Run("Sub")]), ParagraphBlock(runs=[Run("p2")]),
        HeadingBlock(level=1, runs=[Run("Doi")]), ParagraphBlock(runs=[Run("p3")])])]
    new = split_by_headings(b, b.sections[0].id, 1)
    assert [s.title for s in b.sections] == ["Tot", "Unu", "Doi"]
    sub = next(x for x in new[0].blocks if isinstance(x, HeadingBlock))
    assert sub.level == 1  # Heading 2 is promoted under its new section
    assert [x.plain_text() for x in b.sections[0].blocks] == ["p0"]
    merged = merge_with_next(b, b.sections[1].id)
    assert [s.title for s in b.sections] == ["Tot", "Unu"]
    assert [x.plain_text() for x in merged.blocks if x.plain_text()][-2:] == ["Doi", "p3"]  # title kept as heading
    with pytest.raises(SectionToolError):
        merge_with_next(b, b.sections[-1].id)
    with pytest.raises(SectionToolError):
        split_by_headings(b, b.sections[0].id, 3)


def test_poem_labels():
    assert poem_label(PoetryBlock(title="Doina", text="x")) == "Doina"
    assert poem_label(PoetryBlock(title="7", text="Primul vers\nal doilea")) == "7. Primul vers"
    assert poem_label(PoetryBlock(title="", text="")) == "Untitled poem"


def test_layout_of_split_book_still_complete():
    b = poems_book()
    before = " ".join(g.text for p in LayoutEngine().build(b).pages for g in p.items if hasattr(g, "text"))
    split_by_poems(b, b.sections[1].id)
    res = LayoutEngine().build(b)
    after = " ".join(g.text for p in res.pages for g in p.items if hasattr(g, "text"))
    for word in ("Cade", "lumina", "Al", "doilea", "intro", "notă"):
        assert word in after and word in before
    assert not [i for i in res.issues if i.severity in ("error", "warning")]


def test_navigator_split_is_one_undoable_step(window, monkeypatch):
    state, nav = window.state, window.navigator
    ch = chapter(window)
    ch.blocks = [PoetryBlock(title="A", text="x\ny"), PoetryBlock(title="B", text="z\nw")]
    nav.rebuild()
    nav.select(ch.id)
    n = len(list(state.project.walk()))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    nav.split_poems()
    titles = [s.title for s in state.project.walk()]
    assert "A" in titles and "B" in titles and len(titles) == n + 1  # original (now empty) replaced by two
    assert nav.current_id() == next(s.id for s in state.project.walk() if s.title == "A")
    state.undo_stack.undo()
    assert len(list(state.project.walk())) == n and chapter(window).id == ch.id
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    nav.split_headings(1)  # nothing to split: reported, no change
    assert len(list(state.project.walk())) == n
