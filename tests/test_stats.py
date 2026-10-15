from PySide6.QtWidgets import QApplication

from app.domain.book import BookProject
from app.domain.content_blocks import (CodeBlock, HeadingBlock, ImageBlock, ListBlock, ParagraphBlock,
                                       PoetryBlock, Run, TableBlock)
from app.domain.sections import Section
from app.layout.pagination import LayoutEngine
from app.services.stats_service import compute_stats
from app.ui.dialogs.stats_dialog import StatsDialog
from tests.test_ui import chapter, qapp, wait_until, window  # noqa: F401  (fixtures)


def sample():
    b = BookProject()
    b.metadata.title = "Statistici"
    b.sections = [
        Section("Title", "title_page", show_title=False),
        Section("Unu", "chapter", blocks=[
            ParagraphBlock(runs=[Run("unu doi trei patru cinci")]), HeadingBlock(level=1, runs=[Run("Titlu aici")]),
            ListBlock(items=[[Run("a b")], [Run("c")]]), CodeBlock(text="x = 1"),
            TableBlock(rows=[["h"], ["v"]]), ImageBlock(asset="x")]),
        Section("Doi", "chapter", blocks=[PoetryBlock(title="T", text="vers unu\nvers doi\n\nvers trei")]),
        Section("Ascuns", "chapter", enabled=False, blocks=[ParagraphBlock(runs=[Run("nu se numără deloc")])])]
    return b


def test_counts_are_exact():
    st = compute_stats(sample())
    assert st.chapters == 2 and st.sections == 4 and st.hidden_sections == 1
    assert st.paragraphs == 1 and st.headings == 1 and st.list_items == 2
    assert st.poems == 1 and st.verse_lines == 3 and st.longest_poem_lines == 3
    assert st.images == 1 and st.tables == 1 and st.code_blocks == 1
    # 5 words + heading 2 + list 3 + code 3 + table ("h v") 2 + poem (title 1 + 6 words) = 22
    assert st.words == 5 + 2 + 3 + 3 + 2 + 7
    assert st.characters_no_spaces <= st.characters and st.words > 0
    assert st.avg_words_per_chapter == st.words // 2
    assert [c.title for c in st.chapter_stats][0] == "Unu"  # longest first, hidden section excluded
    assert all(c.title != "Ascuns" for c in st.chapter_stats)
    assert st.pages is None


def test_pages_and_reading_time_from_layout():
    b = BookProject()
    b.sections = [Section("A", "chapter", blocks=[ParagraphBlock(runs=[Run("cuvânt " * 2300)])]),
                  Section("B", "chapter", blocks=[ParagraphBlock(runs=[Run("alt " * 300)])])]
    res = LayoutEngine().build(b)
    st = compute_stats(b, res)
    assert st.pages == res.page_count and st.reading_minutes == round(2600 / 230)
    a = next(c for c in st.chapter_stats if c.title == "A")
    assert a.pages and a.pages >= 3
    rows = dict(st.rows())
    assert rows["Pages (current layout)"] == str(res.page_count) and "min" in rows["Estimated reading time"]


def test_dialog_shows_and_copies(window):
    chapter(window).blocks = [ParagraphBlock(runs=[Run("doar cinci cuvinte aici deci")])]
    window.state.request_layout(immediate=True)
    window.state.layout_controller.wait_idle()
    dlg = StatsDialog(window.state, window)
    cells = {dlg.table.item(r, 0).text(): dlg.table.item(r, 1).text() for r in range(dlg.table.rowCount())}
    assert cells["Words"] == "5" and cells["Chapters"] == "1"
    dlg.copy_text()
    assert "Words: 5" in QApplication.clipboard().text()
    dlg.close()
