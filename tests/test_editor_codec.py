import pytest
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from app.domain.book import BookProject
from app.domain.content_blocks import (CodeBlock, ExerciseBlock, HeadingBlock, ImageBlock,
                                       ListBlock, PageBreakBlock, ParagraphBlock, PoetryBlock,
                                       QuoteBlock, RecipeBlock, Run, SceneBreakBlock, TableBlock)
from app.ui.editor.block_codec import blocks_from_document, load_blocks
from tests.conftest import RO


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def roundtrip(blocks, book=None):
    doc = QTextDocument()
    load_blocks(doc, blocks, book)
    originals = {b.id: b for b in blocks}
    return blocks_from_document(doc, originals), doc


def test_roundtrip_preserves_all_block_types(qapp):
    blocks = [
        HeadingBlock(level=2, runs=[Run("Titlu "), Run("italic", italic=True)]),
        ParagraphBlock(runs=[Run("Plain "), Run("bold", bold=True), Run(" "),
                             Run("it", italic=True), Run(" "), Run("ul", underline=True), Run(" "),
                             Run("code", code=True), Run(" "), Run("link", link="https://ex.org"),
                             Run(f" {RO}")]),
        ListBlock(ordered=False, items=[[Run("a")], [Run("b", bold=True)]]),
        ListBlock(ordered=True, items=[[Run("one")], [Run("two")], [Run("three")]]),
        QuoteBlock(runs=[Run("To be")], attribution=[Run("Shakespeare")]),
        CodeBlock(text="def f():\n    return 1\n\nx = 2", language="python", caption=[Run("cap")]),
        PoetryBlock(title="Poem", text="Line 1\nLine 2\n\nStanza 2", one_per_page=True),
        SceneBreakBlock(glyph="***"),
        ExerciseBlock(kind="definition", title="Term", runs=[Run("meaning")]),
        PageBreakBlock(blank=True),
        TableBlock(rows=[["a", "b"]]),
        RecipeBlock(title="Soup"),
        ImageBlock(asset="x", caption=[Run("c")]),
        ParagraphBlock(runs=[]),
    ]
    back, _ = roundtrip(blocks)
    assert len(back) == len(blocks)
    for a, b in zip(blocks, back):
        assert type(a) is type(b)
        assert a.id == b.id, type(a).__name__
        assert a == b, f"{type(a).__name__}\n{a}\n{b}"


def test_stable_ids_when_text_edited(qapp):
    p = ParagraphBlock(runs=[Run("hello")])
    h = HeadingBlock(level=1, runs=[Run("H")])
    doc = QTextDocument()
    load_blocks(doc, [h, p], None)
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(doc)
    c.movePosition(QTextCursor.End)
    c.insertText(" world")
    back = blocks_from_document(doc, {h.id: h, p.id: p})
    assert back[1].id == p.id and back[1].plain_text() == "hello world" and back[0].id == h.id


def test_splitting_paragraph_creates_new_id_not_duplicate(qapp):
    p = ParagraphBlock(runs=[Run("first second")])
    doc = QTextDocument()
    load_blocks(doc, [p], None)
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(doc)
    c.setPosition(5)
    c.insertBlock()
    back = blocks_from_document(doc, {p.id: p})
    assert [b.plain_text() for b in back] == ["first", " second"]
    assert back[0].id == p.id and back[1].id != p.id


def test_deleting_placeholder_text_block_removes_block(qapp):
    img = ImageBlock(asset="a")
    para = ParagraphBlock(runs=[Run("x")])
    doc = QTextDocument()
    load_blocks(doc, [para, img], None)
    from PySide6.QtGui import QTextCursor
    c = QTextCursor(doc.lastBlock())
    c.select(QTextCursor.BlockUnderCursor)
    c.removeSelectedText()
    back = blocks_from_document(doc, {para.id: para, img.id: img})
    assert [type(b).__name__ for b in back] == ["ParagraphBlock"]


def test_poetry_line_breaks_stay_in_one_block(qapp):
    poem = PoetryBlock(text="a\nb\n\nc")
    back, doc = roundtrip([poem])
    assert doc.blockCount() == 1
    assert back[0].text == "a\nb\n\nc"


def test_empty_document_yields_one_paragraph(qapp):
    back, _ = roundtrip([])
    assert len(back) == 1 and isinstance(back[0], ParagraphBlock)


def test_heading_display_formatting_does_not_leak_into_runs(qapp):
    h = HeadingBlock(level=1, runs=[Run("Plain heading")])
    back, _ = roundtrip([h])
    assert back[0].runs == [Run("Plain heading")]
    q = QuoteBlock(runs=[Run("quote")])
    back, _ = roundtrip([q])
    assert back[0].runs == [Run("quote")]
