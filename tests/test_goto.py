from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.domain.book import BookProject
from app.domain.content_blocks import HeadingBlock, ParagraphBlock, PoetryBlock, RecipeBlock, Run
from app.domain.sections import Section
from app.layout.pagination import LayoutEngine
from app.services.navigation_index import build_index, fold, resolve_page, search_index
from app.ui.dialogs.goto_dialog import GoToDialog
from tests.conftest import LOREM
from tests.test_ui import chapter, qapp, wait_until, window  # noqa: F401  (fixtures)


def book():
    b = BookProject()
    b.sections = [
        Section("Title", "title_page", show_title=False),
        Section("Capitolul Întâi", "chapter", blocks=[
            ParagraphBlock(runs=[Run(LOREM * 30)]), HeadingBlock(level=1, runs=[Run("Începutul mării")]),
            ParagraphBlock(runs=[Run(LOREM * 30)])]),
        Section("Poeme", "chapter", blocks=[PoetryBlock(title="Seară", text="a\nb"),
                                            PoetryBlock(title="7", text="Primul vers\nal doilea"),
                                            RecipeBlock(title="Ciorbă de perișoare")]),
        Section("Ascuns", "chapter", enabled=False, blocks=[PoetryBlock(title="Nu apare", text="x\ny")])]
    return b


def test_index_contents_and_hidden_sections_excluded():
    b = book()
    idx = build_index(b, LayoutEngine().build(b))
    kinds = [(e.kind, e.title) for e in idx]
    assert ("section", "Capitolul Întâi") in kinds and ("heading", "Începutul mării") in kinds
    assert ("poem", "Seară") in kinds and ("poem", "7. Primul vers") in kinds
    assert ("recipe", "Ciorbă de perișoare") in kinds
    assert not any("Nu apare" in t or t == "Ascuns" for _, t in kinds)
    assert all(e.page_index is not None for e in idx if e.title != "Title")  # generated pages have no anchor


def test_search_is_diacritic_and_case_insensitive_and_ranked():
    b = book()
    idx = build_index(b)
    assert fold("ȘȚĂÎÂ") == "staia"
    assert [e.title for e in search_index(idx, "inceputul MARII")] == ["Începutul mării"]
    assert [e.title for e in search_index(idx, "capitolul intai")] == ["Capitolul Întâi"]
    ranked = [e.title for e in search_index(idx, "se")]
    assert ranked[0] == "Seară"  # prefix matches first
    assert search_index(idx, "zzz") == [] and len(search_index(idx, "")) == len(idx)


def test_page_resolution_by_label_and_sheet():
    b = book()
    res = LayoutEngine().build(b)
    first_label = next(p for p in res.pages if p.label)
    e = resolve_page(res, first_label.label)
    assert e.kind == "page" and e.page_index == first_label.index
    assert resolve_page(res, "1") is not None and resolve_page(res, "99999") is None
    assert resolve_page(res, "") is None and resolve_page(None, "1") is None


def test_dialog_filters_and_emits(window):
    state = window.state
    state.project.sections.append(Section("Poezii noi", "chapter", blocks=[PoetryBlock(title="Vânt de toamnă", text="x\ny")]))
    state.request_layout(immediate=True)
    state.layout_controller.wait_idle()
    dlg = GoToDialog(state, window)
    got = []
    dlg.chosen.connect(got.append)
    dlg.query.setText("vant toamna")
    assert dlg.list.count() == 1 and "Vânt de toamnă" in dlg.list.item(0).text()
    dlg._accept_current()
    assert got and got[0].kind == "poem" and got[0].block_id
    dlg2 = GoToDialog(state, window)
    dlg2.query.setText("1")
    assert dlg2.list.item(0).text().startswith("□")  # a page match comes first
    dlg2.close()


def test_window_jumps_to_poem_and_page(window):
    state = window.state
    sec = Section("Versuri", "chapter", blocks=[ParagraphBlock(runs=[Run(LOREM * 40)]),
                                                PoetryBlock(title="Doina", text="un vers\naltul")])
    state.project.sections.insert(len(state.project.sections) - 1, sec)
    window.navigator.rebuild()
    state.request_layout(immediate=True)
    state.layout_controller.wait_idle()
    wait_until(lambda: state.layout is not None and sec.id in state.layout.section_pages)
    entry = next(e for e in build_index(state.project, state.layout) if e.kind == "poem" and e.title == "Doina")
    window._go_to_entry(entry)
    assert window.navigator.current_id() == sec.id and window.tabs.currentWidget() is window.editor
    page = resolve_page(state.layout, "2")
    window._go_to_entry(page)
    assert window.tabs.currentWidget() is window.preview and window.preview.current == page.page_index
