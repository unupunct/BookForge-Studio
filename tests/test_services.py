import json
import time
import zipfile
from pathlib import Path

import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import (CodeBlock, HeadingBlock, ImageBlock, ListBlock,
                                       ParagraphBlock, PoetryBlock, Run, TableBlock)
from app.domain.sections import Section
from app.domain.styles import StyleDefinition, StyleSet, default_styles, merge_template_styles
from app.persistence.project_archive import load_project, save_project
from app.services.autosave_service import AutosaveService
from app.services.project_service import (PROFILES, NewBookSpec, SettingsStore, create_project)
from app.services.search_service import (SearchOptions, replace_in_book, replace_one, search_book)
from app.services.template_service import (TemplateError, TemplateService, apply_template,
                                           sample_book, template_from_book)
from app.services.validation_service import validate_book
from app.layout.pagination import LayoutEngine
from tests.conftest import RO, make_png


# ---------------------------------------------------------------- styles
def test_style_inheritance_and_change_propagates():
    styles = default_styles()
    ss = StyleSet(styles)
    assert ss.resolve("heading2").bold is True  # inherited from heading1
    assert ss.resolve("heading2").font_size == 14  # overridden
    before = ss.resolve("heading3").color
    styles["heading1"].color = "#336699"
    assert StyleSet(styles).resolve("heading3").color == "#336699" != before


def test_template_does_not_overwrite_user_customised_style():
    styles = default_styles()
    styles["chapter_title"].font_size = 40
    styles["chapter_title"].user_modified = True
    merged = merge_template_styles(styles, {"chapter_title": {"font_size": 10},
                                            "heading1": {"font_size": 19}})
    assert merged["chapter_title"].font_size == 40
    assert merged["heading1"].font_size == 19 and merged["heading1"].user_modified is False
    forced = merge_template_styles(styles, {"chapter_title": {"font_size": 10}}, False)
    assert forced["chapter_title"].font_size == 10


def test_body_settings_drive_derived_styles():
    from app.layout.page_builder import BuildContext
    b = BookProject()
    b.settings.body_font = "Times New Roman"
    b.settings.body_size = 13
    ctx = BuildContext(b)
    assert ctx.style("body").font_family == "Times New Roman"
    assert ctx.style("block_quote").font_family == "Times New Roman"
    assert ctx.style("block_quote").font_size == 13


# ------------------------------------------------------------- templates
def test_thirteen_builtin_templates_load_and_apply():
    svc = TemplateService()
    tpls = svc.list_templates()
    assert len(tpls) >= 13
    required = {"modern_novel", "classic_novel", "minimalist_poetry", "contemporary_poetry",
                "technical_handbook", "it_documentation", "academic_textbook",
                "illustrated_children", "cookbook", "biography", "business_nonfiction",
                "photo_heavy", "general_purpose"}
    assert required <= {t["key"] for t in tpls}
    for t in tpls:
        book = sample_book(t)
        res = LayoutEngine().build(book)
        assert res.page_count >= 1 and res.pages[0].items
        assert abs(book.settings.width_mm - t["settings"]["width_mm"]) < 0.01
        assert book.settings.template == t["key"]


def test_template_duplicate_export_import_reset(tmp_path):
    svc = TemplateService()
    dup = svc.duplicate("modern_novel", "My Novel")
    assert dup["key"] == "my_novel" and not dup["builtin"]
    assert any(t["key"] == "my_novel" for t in svc.list_templates())
    out = tmp_path / "t.json"
    svc.export_template("my_novel", out)
    svc.delete_user("my_novel")
    imported = svc.import_template(out)
    assert imported["key"] == "my_novel"
    # customising a built-in keeps a user override that reset removes
    t = json.loads(json.dumps(svc.get("cookbook")))
    t["settings"]["body_size"] = 14
    svc.customise_builtin("cookbook", t)
    assert svc.get("cookbook")["settings"]["body_size"] == 14
    assert svc.reset("cookbook") is True
    assert svc.get("cookbook")["settings"]["body_size"] != 14
    with pytest.raises(TemplateError):
        svc.get("nope")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(TemplateError):
        svc.import_template(bad)


def test_apply_template_keeps_content_and_metadata(sample_book):
    before_blocks = [b.plain_text() for s in sample_book.sections for b in s.blocks]
    title = sample_book.metadata.title
    apply_template(sample_book, TemplateService().get("technical_handbook"))
    assert [b.plain_text() for s in sample_book.sections for b in s.blocks] == before_blocks
    assert sample_book.metadata.title == title
    assert sample_book.settings.page_size == "A4"


def test_template_from_book_roundtrip(sample_book):
    sample_book.styles["heading1"].font_size = 30
    sample_book.styles["heading1"].user_modified = True
    t = template_from_book(sample_book, "Mine", "mine")
    assert t["styles"]["heading1"]["font_size"] == 30
    other = BookProject()
    apply_template(other, t)
    assert other.styles["heading1"].font_size == 30


# ---------------------------------------------------------- project service
def test_all_profiles_create_valid_projects_that_layout():
    for key in PROFILES:
        book = create_project(NewBookSpec(title="Țara Minunilor", author="A", profile=key))
        assert book.metadata.category == key
        kinds = [s.kind for s in book.sections]
        assert "chapter" in kinds and "title_page" in kinds
        res = LayoutEngine().build(book)
        assert res.page_count >= 3


def test_wizard_options_applied():
    book = create_project(NewBookSpec(title="X", profile="novel", page_size="A4", cover=False,
                                      toc=False, chapters_new_page=False, output="print"))
    kinds = [s.kind for s in book.sections]
    assert "front_cover" not in kinds and "toc" not in kinds and "back_cover" not in kinds
    assert book.settings.page_size == "A4" and book.settings.chapter_new_page is False
    assert book.settings.export_profile == "print"


def test_settings_store_recent(tmp_path):
    s = SettingsStore(tmp_path / "s.json")
    a = tmp_path / "a.bookforge"
    a.write_bytes(b"x")
    s.add_recent(a)
    s.add_recent(tmp_path / "gone.bookforge")
    assert SettingsStore(tmp_path / "s.json").existing_recent() == [str(a.resolve())]


# --------------------------------------------------------------- autosave
def test_autosave_and_recovery(tmp_path, sample_book):
    svc = AutosaveService(tmp_path / "rec")
    (tmp_path / "rec").mkdir()
    original = tmp_path / "orig.bookforge"
    save_project(sample_book, original)
    time.sleep(0.05)
    sample_book.metadata.title = "Edited but unsaved"
    svc.request(sample_book, original)
    assert svc.wait_idle()
    assert svc.last_error is None
    cands = svc.candidates()
    assert len(cands) == 1 and cands[0].title == "Edited but unsaved"
    assert svc.load(cands[0]).metadata.title == "Edited but unsaved"
    svc.discard(sample_book.id)
    assert svc.candidates() == []


def test_autosave_ignored_after_later_manual_save(tmp_path, sample_book):
    svc = AutosaveService(tmp_path / "rec")
    (tmp_path / "rec").mkdir()
    original = tmp_path / "orig.bookforge"
    svc.request(sample_book, original)
    svc.wait_idle()
    time.sleep(0.05)
    save_project(sample_book, original)
    assert svc.candidates() == []


def test_autosave_coalesces_and_survives_errors(tmp_path, sample_book):
    svc = AutosaveService(tmp_path / "rec")
    (tmp_path / "rec").mkdir()
    for i in range(5):
        sample_book.metadata.title = f"v{i}"
        svc.request(sample_book, None)
    assert svc.wait_idle()
    assert svc.load(svc.candidates()[0]).metadata.title == "v4"
    (tmp_path / "rec").rename(tmp_path / "gone")  # directory vanishes: must not raise
    (tmp_path / "gone").rename(tmp_path / "rec2")
    svc.request(sample_book, None)
    assert svc.wait_idle()


# ------------------------------------------------------------- validation
def test_validation_reports(tmp_path):
    b = BookProject()
    rep = validate_book(b)
    assert any(i.code == "empty_book" for i in rep.errors) and any(i.code == "no_title" for i in rep.warnings)
    a = b.add_asset(make_png(40, 30), "small.png")
    b.metadata.title = "T"
    b.sections = [Section("C", "chapter", blocks=[
        ParagraphBlock(runs=[Run("text")]), ImageBlock(asset=a.id, width_pct=100),
        ImageBlock(asset="ghost"), ParagraphBlock(runs=[Run("emoji \U0001F600 中")])]),
        Section("Empty", "chapter")]
    layout = LayoutEngine().build(b)
    rep = validate_book(b, layout, "print")
    codes = {i.code for i in rep.issues}
    assert {"missing_asset", "low_resolution", "missing_glyphs", "empty_section"} <= codes
    low = [i for i in rep.issues if i.code == "low_resolution"][0]
    assert low.severity == "error" and low.page_index is not None
    rep_digital = validate_book(b, layout, "digital")
    assert [i for i in rep_digital.issues if i.code == "low_resolution"][0].severity in ("error", "warning")
    glyph = next(i for i in rep.issues if i.code == "missing_glyphs")
    assert glyph.block_id and glyph.section_id


def test_validation_clean_book(sample_book):
    sample_book.sections = [s for s in sample_book.sections if s.kind != "toc"]
    layout = LayoutEngine().build(sample_book)
    rep = validate_book(sample_book, layout)
    assert rep.ok and not rep.warnings


# ----------------------------------------------------------------- search
@pytest.fixture
def search_book_fixture():
    b = BookProject()
    b.sections = [
        Section("One", "chapter", blocks=[
            HeadingBlock(level=1, runs=[Run("The Cat chapter")]),
            ParagraphBlock(runs=[Run("The cat sat. "), Run("CAT", bold=True), Run(" and concatenate.")]),
            CodeBlock(text="cat file.txt"), ListBlock(items=[[Run("a cat")]]),
            TableBlock(rows=[["cat", "dog"]], caption=[Run("cat table")]),
            ImageBlock(asset="x", caption=[Run("cat photo")])]),
        Section("Two", "chapter", blocks=[ParagraphBlock(runs=[Run(f"Pisica {RO}")]),
                                           ParagraphBlock(runs=[Run("cat locked")], locked=True)]),
        Section("Hidden", "chapter", enabled=False, blocks=[ParagraphBlock(runs=[Run("cat hidden")])])]
    return b


def test_search_options(search_book_fixture):
    b = search_book_fixture
    all_hits = search_book(b, "cat")
    assert {h.block_type for h in all_hits} >= {"heading", "paragraph", "code", "list", "table", "image"}
    assert not any("hidden" in h.snippet for h in all_hits)
    assert len(search_book(b, "cat", SearchOptions(case_sensitive=True))) < len(all_hits)
    whole = search_book(b, "cat", SearchOptions(whole_word=True))
    assert not any(h.matched == "cat" and "concatenate" in h.snippet and h.start > 20 for h in whole)
    assert len(whole) < len(all_hits)
    assert not search_book(b, "cat", SearchOptions(headings=False, code=False, captions=False, tables=False,
                                                    current_section_id=b.sections[1].id))[1:]
    assert not any(h.block_type == "code" for h in search_book(b, "cat", SearchOptions(code=False)))
    assert search_book(b, "cat", SearchOptions(include_hidden=True)).__len__() == len(all_hits) + 1
    assert search_book(b, "Pisica")[0].section_title == "Two"
    assert search_book(b, "ș") and search_book(b, "ȘTEFAN")  # diacritics, case-insensitive
    assert search_book(b, "") == []


def test_replace_all_preserves_formatting_and_respects_locks(search_book_fixture):
    b = search_book_fixture
    res = replace_in_book(b, "cat", "dog", SearchOptions(case_sensitive=True, whole_word=True))
    assert res.replaced >= 5 and res.skipped_locked == 1
    para = b.sections[0].blocks[1]
    assert para.plain_text() == "The dog sat. CAT and concatenate."
    assert any(r.bold and r.text == "CAT" for r in para.runs)
    assert b.sections[1].blocks[1].plain_text() == "cat locked"  # locked untouched
    assert b.sections[0].blocks[2].text == "dog file.txt"
    assert b.sections[0].blocks[4].rows == [["dog", "dog"]]


def test_replace_across_formatting_boundary():
    b = BookProject()
    b.sections = [Section("S", "chapter", blocks=[ParagraphBlock(runs=[
        Run("hello wor"), Run("ld", bold=True), Run(" again")])])]
    res = replace_in_book(b, "world", "planet")
    assert res.replaced == 1
    assert b.sections[0].blocks[0].plain_text() == "hello planet again"


def test_replace_one(search_book_fixture):
    b = search_book_fixture
    hits = search_book(b, "cat", SearchOptions(current_section_id=b.sections[0].id))
    para_hits = [h for h in hits if h.block_type == "paragraph"]
    assert replace_one(b, para_hits[0], "cat", "bird")
    assert b.sections[0].blocks[1].plain_text().startswith("The bird sat.")
    assert "CAT" in b.sections[0].blocks[1].plain_text()
    locked = search_book(b, "locked")[0]
    assert replace_one(b, locked, "locked", "x") is False


# --------------------------------------------------------------- reliability
def test_large_manuscript_roundtrip_and_search(tmp_path):
    b = BookProject()
    for i in range(300):
        b.sections.append(Section(f"Chapter {i}", "chapter", blocks=[
            ParagraphBlock(runs=[Run(f"paragraph {j} of chapter {i} " * 12)]) for j in range(20)]))
    t = time.perf_counter()
    p = tmp_path / "big.bookforge"
    save_project(b, p)
    again = load_project(p)
    hits = search_book(again, "chapter 299")
    elapsed = time.perf_counter() - t
    assert len(again.sections) == 300 and len(hits) == 240
    assert elapsed < 15, f"6000 blocks save/load/search took {elapsed:.1f}s"
