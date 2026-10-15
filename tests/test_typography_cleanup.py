from PySide6.QtWidgets import QMessageBox

from app.domain.book import BookProject
from app.domain.content_blocks import CodeBlock, ListBlock, ParagraphBlock, PoetryBlock, Run
from app.domain.sections import Section
from app.services.typography_service import CleanupOptions, cleanup_book
from app.ui.dialogs.typography_dialog import TypographyDialog
from tests.test_ui import chapter, qapp, wait_until, window  # noqa: F401  (fixtures)


def book_with(*blocks):
    b = BookProject()
    b.sections = [Section("C", "chapter", blocks=list(blocks))]
    return b


def text(b):
    return b.sections[0].blocks[0].plain_text()


def test_romanian_quotes_dashes_ellipsis_spaces():
    b = book_with(ParagraphBlock(runs=[Run('El a spus: "Nu știu..." și -- apoi  a plecat . - Ce zici?')]))
    rep = cleanup_book(b, CleanupOptions(quotes="ro"))
    assert text(b) == "El a spus: „Nu știu…” și — apoi a plecat. — Ce zici?"
    assert rep.counts["quotes"] == 2 and rep.counts["ellipsis"] == 1 and rep.blocks_changed == 1


def test_dialogue_dash_and_apostrophes_and_other_quote_styles():
    b = book_with(ParagraphBlock(runs=[Run("- Salut, n'am timp.")]))
    cleanup_book(b, CleanupOptions(quotes=None))
    assert text(b) == "— Salut, n’am timp."
    e = book_with(ParagraphBlock(runs=[Run('She said "hello" and (\"bye\").')]))
    cleanup_book(e, CleanupOptions(quotes="en"))
    assert text(e) == "She said “hello” and (“bye”)."
    f = book_with(ParagraphBlock(runs=[Run('Il dit "oui".')]))
    cleanup_book(f, CleanupOptions(quotes="fr"))
    assert text(f) == "Il dit « oui »."
    g = book_with(ParagraphBlock(runs=[Run('Er sagte "ja".')]))
    cleanup_book(g, CleanupOptions(quotes="de"))
    assert text(g) == "Er sagte „ja“."


def test_formatting_survives_and_quotes_pair_across_runs():
    p = ParagraphBlock(runs=[Run('Text "citat '), Run("aldin", bold=True), Run('" final')])
    b = book_with(p)
    cleanup_book(b, CleanupOptions(quotes="ro"))
    assert text(b) == "Text „citat aldin” final"
    assert [(r.text, r.bold) for r in b.sections[0].blocks[0].runs] == [
        ("Text „citat ", False), ("aldin", True), ("” final", False)]


def test_code_and_locked_blocks_untouched_poetry_cleaned():
    code = CodeBlock(text='print("a")  # ... --')
    locked = ParagraphBlock(runs=[Run('"x"...')], locked=True)
    poem = PoetryBlock(text='- Spune "da"...\nși  apoi', title='"Titlu"')
    b = book_with(code, locked, poem, ListBlock(items=[[Run('un "item"')]]))
    rep = cleanup_book(b, CleanupOptions(quotes="ro"))
    blocks = b.sections[0].blocks
    assert blocks[0].text == 'print("a")  # ... --'
    assert blocks[1].plain_text() == '"x"...' and rep.skipped_locked == 1
    assert blocks[2].text == "— Spune „da”…\nși apoi" and blocks[2].title == "„Titlu”"
    assert blocks[3].plain_text() == "un „item”"
    b2 = book_with(PoetryBlock(text='"a"'))
    cleanup_book(b2, CleanupOptions(quotes="ro", include_poetry=False))
    assert b2.sections[0].blocks[0].text == '"a"'


def test_dry_run_changes_nothing_and_is_idempotent():
    b = book_with(ParagraphBlock(runs=[Run('"a"... b')]))
    before = b.sections[0].blocks[0].to_dict()
    rep = cleanup_book(b, CleanupOptions(quotes="ro"), apply=False)
    assert rep.total >= 3 and b.sections[0].blocks[0].to_dict() == before
    cleanup_book(b, CleanupOptions(quotes="ro"))
    again = cleanup_book(b, CleanupOptions(quotes="ro"))
    assert again.total == 0 and again.blocks_changed == 0


def test_hyphenated_words_and_apostrophe_quotes_are_not_mangled():
    b = book_with(ParagraphBlock(runs=[Run("o carte bine-venită, 2-3 zile, într-o oră. Z'ana")]))
    cleanup_book(b, CleanupOptions(quotes="ro"))
    assert text(b) == "o carte bine-venită, 2-3 zile, într-o oră. Z’ana"


def test_dialog_counts_applies_and_undo(window, monkeypatch):
    state = window.state
    chapter(window).blocks = [ParagraphBlock(runs=[Run('Un "test"... - da')])]
    window.editor.load_section(chapter(window).id)
    state.project.metadata.language = "ro"
    dlg = TypographyDialog(state, window)
    assert dlg.quotes.currentData() == "ro" and dlg.apply_btn.isEnabled()
    assert "Would change" in dlg.result.text()
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    hits = []
    dlg.applied.connect(lambda: hits.append(1))
    dlg._apply()
    assert hits and chapter(window).blocks[0].plain_text() == "Un „test”… — da"
    state.undo_stack.undo()
    assert chapter(window).blocks[0].plain_text() == 'Un "test"... - da'
