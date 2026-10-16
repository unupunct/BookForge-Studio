"""Page layouts: columns, per-section page setup, wrapped and pinned images, text boxes, designed pages,
and editing of pinned items in the preview."""
import zipfile

import pymupdf
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest

from app.domain.book import BookProject
from app.domain.content_blocks import (ImageBlock, LayoutBlock, ParagraphBlock, Run, TextBoxBlock)
from app.domain.layouts import MM_TO_PT
from app.domain.page_setup import merge_page_dicts, setup_for
from app.domain.sections import Section
from app.layout.model import Glyphs, ImageItem
from app.layout.pagination import LayoutEngine
from app.persistence.project_archive import load_project, save_project
from app.services.epub_check import check_epub
from app.services.export_service import export_other, export_pdf
from app.services.validation_service import validate_book
from tests.conftest import LOREM, make_png
from tests.test_ui import qapp, wait_until, window  # noqa: F401  (fixtures)

TEXT = (LOREM + " ") * 2


def paras(n, text=TEXT):
    return [ParagraphBlock(runs=[Run(text)]) for _ in range(n)]


def book_with(*sections, language="en"):
    b = BookProject()
    b.metadata.title, b.metadata.language = "T", language
    b.settings.facing_pages = False
    b.settings.mirrored_margins = False
    b.settings.chapter_right_page = False
    b.sections = list(sections)
    return b


def add_image(b, w=600, h=400):
    return b.add_asset(make_png(w, h, (40, 120, 200)), "pic.png").id


def glyphs(page):
    return [g for g in page.items if isinstance(g, Glyphs) and g.text.strip()]


# ------------------------------------------------------------------ page setup model
def test_setup_inheritance_and_invalid_values_are_ignored():
    b = BookProject()
    base = setup_for(b.settings, "main")
    assert base.columns == 1 and base.width == pytest.approx(b.settings.width_mm * MM_TO_PT)
    page = merge_page_dicts({"columns": 2, "margins": {"top": 10}}, {"margins": {"bottom": 12}, "column_gap_mm": 6})
    assert page == {"columns": 2, "margins": {"top": 10, "bottom": 12}, "column_gap_mm": 6}
    s = setup_for(b.settings, "main", page)
    assert s.columns == 2 and s.margins[0] == pytest.approx(10 * MM_TO_PT) and s.margins[1] == pytest.approx(12 * MM_TO_PT)
    assert s.column_width < s.content_width / 2 + 1
    junk = setup_for(b.settings, "main", {"columns": "x", "width_mm": "wide", "height_mm": 99999, "page_size": "Nope",
                                          "margins": {"top": -5, "left": 3, "bottom": 9999}})
    assert junk.columns == 1 and junk.width == base.width and junk.margins[0] == base.margins[0]
    assert setup_for(b.settings, "main", {"columns": 99}).columns == 4


def test_section_page_survives_save_and_load(tmp_path):
    sec = Section("C", "chapter", blocks=paras(1))
    sec.page = {"columns": 3, "column_gap_mm": 5, "page_size": "A6"}
    b = book_with(sec)
    path = tmp_path / "b.bookforge"
    save_project(b, path)
    back = load_project(path)
    assert back.sections[0].page == {"columns": 3, "column_gap_mm": 5, "page_size": "A6"}
    assert Section.from_dict({"title": "old", "kind": "chapter"}).page == {}  # projects without the key still load


# ------------------------------------------------------------------ columns
def test_two_columns_fill_left_then_right_and_the_title_spans_the_page():
    sec = Section("Titlu foarte lung pentru coloane", "chapter", blocks=paras(14))
    sec.page = {"columns": 2, "column_gap_mm": 8}
    b = book_with(sec)
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if len(glyphs(p)) > 20)
    x0, top, x1, bottom = page.content_box
    gap = 8 * MM_TO_PT
    cw = (x1 - x0 - gap) / 2
    body = [g for g in glyphs(page) if g.size < 14]
    left = [g for g in body if g.x < x0 + cw + 1]
    right = [g for g in body if g.x >= x0 + cw + gap - 1]
    assert left and right and len(left) + len(right) == len(body)
    assert max(g.x + g.width for g in left) <= x0 + cw + 1.5 and max(g.x + g.width for g in right) <= x1 + 1.5
    # both columns start at the same height, below the title
    assert min(g.y for g in left) == pytest.approx(min(g.y for g in right), abs=0.01)
    title = [g for g in glyphs(page) if g.size >= 14]
    assert title and max(g.y for g in title) < min(g.y for g in body)
    # a column layout holds more words per page than a single column of the same text would show on one page
    single = LayoutEngine().build(book_with(Section("T", "chapter", blocks=paras(14))))
    assert res.page_count <= single.page_count + 1


def test_columns_keep_every_word_and_end_cleanly_for_the_next_section(tmp_path):
    cols = Section("Coloane", "chapter", blocks=paras(9))
    cols.page = {"columns": 2}
    after = Section("Dupa", "section", blocks=[ParagraphBlock(runs=[Run("Dupa coloane urmeaza textul normal.")])])
    b = book_with(cols, after)
    res = LayoutEngine().build(b)
    for p in res.pages:
        for g in p.items:
            if isinstance(g, Glyphs):
                assert p.content_box[0] - 0.5 <= g.x and g.x + g.width <= p.content_box[2] + 1.5
    out = tmp_path / "c.pdf"
    export_pdf(b, out, "digital", allow_errors=True)
    text = " ".join(pg.get_text() for pg in pymupdf.open(str(out)))
    assert text.count("consectetur") == 9 * 2 and "Dupa coloane urmeaza" in text
    last = res.pages[-1]
    normal = [g for g in glyphs(last) if g.text.startswith("Dupa")]
    others = [g for g in glyphs(last) if not g.text.startswith("Dupa") and g.size < 14]
    if normal and others:  # the single-column text begins below everything the columns used
        assert normal[0].y > max(g.y for g in others) - 0.01


def test_columns_do_not_apply_to_generated_pages():
    toc = Section("Cuprins", "toc")
    toc.page = {"columns": 2}
    ch = Section("C", "chapter", blocks=paras(1))
    res = LayoutEngine().build(book_with(toc, ch))
    page = res.pages[0]
    x0, _, x1, _ = page.content_box
    assert max(g.x + g.width for g in glyphs(page)) > x0 + (x1 - x0) * 0.95  # page numbers reach the full-width edge


# ------------------------------------------------------------------ page size and margins per section
def test_section_with_its_own_page_size_and_margins(tmp_path):
    a = Section("A", "chapter", blocks=paras(3))
    small = Section("Mica", "chapter", blocks=paras(3))
    small.page = {"width_mm": 100, "height_mm": 140, "margins": {"top": 8, "bottom": 8, "inner": 9, "outer": 9}}
    child = Section("Copil", "section", blocks=paras(1))
    small.children = [child]
    z = Section("Z", "chapter", blocks=paras(3))
    b = book_with(a, small, z)
    res = LayoutEngine().build(b)
    sizes = [(round(p.width), round(p.height)) for p in res.pages]
    big, little = sizes[0], (round(100 * MM_TO_PT), round(140 * MM_TO_PT))
    assert big != little and little in sizes and sizes[-1] == big
    first_small = next(p for p in res.pages if (round(p.width), round(p.height)) == little)
    assert first_small.content_box[0] == pytest.approx(9 * MM_TO_PT) and first_small.content_box[1] == pytest.approx(8 * MM_TO_PT)
    assert res.pages[res.section_pages[small.id] - 1].width == res.pages[0].width  # earlier page unchanged
    out = tmp_path / "m.pdf"
    r = export_pdf(b, out, "digital", allow_errors=True)  # verification checks every page's size
    assert r.pages == res.page_count
    got = [(round(pg.rect.width), round(pg.rect.height)) for pg in pymupdf.open(str(out))]
    assert got == sizes
    r2 = export_pdf(b, tmp_path / "p.pdf", "print", allow_errors=True)  # print adds bleed per page
    assert r2.pages == res.page_count


def test_changing_margins_mid_page_starts_a_new_page():
    a = Section("A", "chapter", blocks=paras(1))
    wide = Section("B", "section", blocks=paras(1))
    wide.page = {"margins": {"inner": 40, "outer": 40}}
    res = LayoutEngine().build(book_with(a, wide))
    pa = res.pages[res.section_pages[a.id]]
    pb = res.pages[res.section_pages[wide.id]]
    assert pb.index > pa.index and pb.content_box[0] > pa.content_box[0]


def test_screen_edition_ignores_section_page_setup(tmp_path):
    sec = Section("A", "chapter", blocks=paras(6))
    sec.page = {"columns": 2, "width_mm": 300, "height_mm": 400}
    out = tmp_path / "s.pdf"
    export_pdf(book_with(sec), out, "screen", allow_errors=True)
    sizes = {(round(p.rect.width), round(p.rect.height)) for p in pymupdf.open(str(out))}
    assert sizes == {(round(108 * MM_TO_PT), round(192 * MM_TO_PT))}


# ------------------------------------------------------------------ wrapped images
def test_floated_image_has_text_beside_it_and_full_width_text_below():
    b = book_with()
    aid = add_image(b)
    sec = Section("C", "chapter", blocks=[
        ImageBlock(asset=aid, width_pct=40, place="wrap_left", caption=[Run("Legenda")])] + paras(3))
    b.sections = [sec]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if any(isinstance(i, ImageItem) for i in p.items))
    img = next(i for i in page.items if isinstance(i, ImageItem))
    x0, top, x1, _ = page.content_box
    assert img.x == pytest.approx(x0) and img.w == pytest.approx((x1 - x0) * 0.4, rel=0.01)
    body = [g for g in glyphs(page) if g.size < 14 and g.text != "Legenda"]
    beside = [g for g in body if img.y <= g.y <= img.y + img.h]
    below = [g for g in body if g.y > img.y + img.h + 14]
    assert beside and below
    assert all(g.x >= img.x + img.w - 0.5 for g in beside)  # nothing runs over the image
    assert min(g.x for g in below) == pytest.approx(x0, abs=1.0)  # the text returns to the full width
    assert any(g.text == "Legenda" for g in glyphs(page))


def test_floated_image_right_and_no_text_is_lost(tmp_path):
    b = book_with()
    aid = add_image(b, 400, 600)
    blocks = [ImageBlock(asset=aid, width_pct=30, place="wrap_right")] + paras(4)
    b.sections = [Section("C", "chapter", blocks=blocks)]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if any(isinstance(i, ImageItem) for i in p.items))
    img = next(i for i in page.items if isinstance(i, ImageItem))
    assert img.x + img.w == pytest.approx(page.content_box[2], abs=0.5)
    beside = [g for g in glyphs(page) if img.y <= g.y <= img.y + img.h]
    assert beside and all(g.x + g.width <= img.x + 0.5 for g in beside)
    out = tmp_path / "w.pdf"
    export_pdf(b, out, "digital", allow_errors=True)
    text = " ".join(pg.get_text() for pg in pymupdf.open(str(out)))
    assert text.count("consectetur") == 4 * 2


def test_floated_image_without_following_text_still_lays_out_and_missing_asset_is_an_error():
    b = book_with()
    b.sections = [Section("C", "chapter", blocks=[ImageBlock(asset=add_image(b), width_pct=50, place="wrap_left"),
                                                    ImageBlock(asset="nope", width_pct=50, place="wrap_right")])]
    res = LayoutEngine().build(b)
    assert any(isinstance(i, ImageItem) for p in res.pages for i in p.items)
    assert any(i.code == "missing_asset" for i in res.issues)


# ------------------------------------------------------------------ pinned images and text boxes
def test_pinned_image_sits_at_its_spot_and_does_not_move_the_text():
    b = book_with()
    aid = add_image(b)
    blocks = paras(4)
    b.sections = [Section("C", "chapter", blocks=list(blocks))]
    ref = LayoutEngine().build(b)
    pin = ImageBlock(asset=aid, place="page", px=0.5, py=0.55, pw=0.3, rotation=10, opacity=0.5)
    b.sections = [Section("C", "chapter", blocks=blocks[:2] + [pin] + blocks[2:])]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if any(isinstance(i, ImageItem) for i in p.items))
    img = next(i for i in page.items if isinstance(i, ImageItem))
    assert img.x == pytest.approx(0.5 * page.width) and img.y == pytest.approx(0.55 * page.height)
    assert img.w == pytest.approx(0.3 * page.width) and img.rot == 10 and img.opacity == 0.5
    assert [(round(g.x, 2), round(g.y, 2), g.text) for p in res.pages for g in glyphs(p)] ==            [(round(g.x, 2), round(g.y, 2), g.text) for p in ref.pages for g in glyphs(p)]
    assert res.page_count == ref.page_count


def test_pinned_image_off_the_page_and_missing_are_reported():
    b = book_with()
    b.sections = [Section("C", "chapter", blocks=[
        ImageBlock(asset=add_image(b), place="page", px=3.0, py=3.0, pw=0.2),
        ImageBlock(asset="gone", place="page")])]
    codes = {i.code for i in LayoutEngine().build(b).issues}
    assert {"off_page", "missing_asset"} <= codes


def test_text_box_draws_its_text_and_background_inside_its_box():
    box = TextBoxBlock(text="Salut\nlume", px=0.2, py=0.3, pw=0.4, ph=0.1, size=14, background="#FFE9A8",
                       align="center", valign="middle", color="#112233")
    b = book_with(Section("C", "chapter", blocks=paras(1) + [box]))
    res = LayoutEngine().build(b)
    page = res.pages[0]
    W, H = page.width, page.height
    texts = [g for g in glyphs(page) if g.color == "#112233"]
    assert {g.text for g in texts} == {"Salut", "lume"}
    assert all(0.2 * W <= g.x and g.x + g.width <= 0.6 * W and 0.3 * H <= g.y <= 0.4 * H + 1 for g in texts)
    bg = [i for i in page.items if getattr(i, "fill", None) == "#FFE9A8"]
    assert bg and bg[0].x == pytest.approx(0.2 * W) and bg[0].w == pytest.approx(0.4 * W)
    assert all(getattr(i, "block_id", None) == box.id for i in texts + bg)


def test_text_box_that_cannot_fit_is_reported_and_autofit_shrinks():
    tiny = TextBoxBlock(text="x " * 400, px=0.1, py=0.1, pw=0.1, ph=0.03, size=12, autofit=False)
    fit = TextBoxBlock(text="Un text mai lung care trebuie sa incapa", px=0.1, py=0.1, pw=0.3, ph=0.05, size=30, autofit=True)
    res = LayoutEngine().build(book_with(Section("C", "chapter", blocks=[tiny])))
    assert any(i.code == "textbox_overflow" for i in res.issues)
    res = LayoutEngine().build(book_with(Section("C", "chapter", blocks=[fit])))
    sizes = [g.size for p in res.pages for g in glyphs(p)]
    assert sizes and max(sizes) < 30 and not any(i.code == "textbox_overflow" for i in res.issues)


# ------------------------------------------------------------------ designed pages
def test_photo_page_is_full_bleed_with_the_caption_on_an_overlay():
    b = book_with()
    blk = LayoutBlock(layout="photo_full", asset=add_image(b), headline="Marea", text="O zi de iarna.", overlay="bottom")
    b.sections = [Section("C", "chapter", blocks=[blk])]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if p.full_bleed)
    img = next(i for i in page.items if isinstance(i, ImageItem))
    assert (img.x, img.y) == (0, 0) and img.w == pytest.approx(page.width) and img.h == pytest.approx(page.height)
    assert img.crop is not None  # centre-cropped to fill, never stretched
    words = {g.text for g in glyphs(page)}
    assert "Marea" in words
    assert min(g.y for g in glyphs(page)) > page.height * 0.6  # on the bottom band
    assert not page.label and res.block_pages[blk.id] == [page.index]
    top = LayoutBlock(layout="photo_full", asset=blk.asset, headline="Sus", overlay="top")
    b.sections = [Section("C", "chapter", blocks=[top])]
    page = next(p for p in LayoutEngine().build(b).pages if p.full_bleed)
    assert max(g.y for g in glyphs(page)) < page.height * 0.4
    none = LayoutBlock(layout="photo_full", asset=blk.asset, headline="Ascuns", overlay="none")
    b.sections = [Section("C", "chapter", blocks=[none])]
    page = next(p for p in LayoutEngine().build(b).pages if p.full_bleed)
    assert not glyphs(page)


@pytest.mark.parametrize("kind", ["image_left", "image_right", "image_top"])
def test_image_and_text_pages_stay_inside_the_margins_and_keep_their_page_number(kind):
    b = book_with()
    blk = LayoutBlock(layout=kind, asset=add_image(b), headline="Fig", text=TEXT, image_pct=40)
    b.sections = [Section("C", "chapter", blocks=paras(1) + [blk])]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if blk.id in {getattr(i, "block_id", None) for i in p.items})
    x0, top, x1, bottom = page.content_box
    img = next(i for i in page.items if isinstance(i, ImageItem))
    assert x0 - 0.5 <= img.x and img.x + img.w <= x1 + 0.5 and top - 0.5 <= img.y and img.y + img.h <= bottom + 0.5
    text = [g for g in glyphs(page) if g.size > 5 and g.text != "Fig"]
    assert text and all(g.x >= x0 - 0.5 and g.x + g.width <= x1 + 1.0 and g.y <= bottom + 1 for g in text)
    if kind == "image_left":
        assert all(g.x >= img.x + img.w for g in text)
    if kind == "image_right":
        assert all(g.x + g.width <= img.x + 0.5 for g in text)
    if kind == "image_top":
        assert all(g.y > img.y + img.h for g in text)
    assert not page.full_bleed and page.label  # numbered like any other page


def test_quote_page_is_centred_and_a_missing_image_is_an_error():
    b = book_with()
    blk = LayoutBlock(layout="quote_page", text="Nu tot timpul e doar timp.", headline="— Unupunct", align="center")
    bad = LayoutBlock(layout="image_left", asset="gone", text="x")
    b.sections = [Section("C", "chapter", blocks=[blk, bad])]
    res = LayoutEngine().build(b)
    page = next(p for p in res.pages if blk.id in {getattr(i, "block_id", None) for i in p.items})
    x0, _, x1, _ = page.content_box
    line = max(glyphs(page), key=lambda g: g.size)
    assert abs((line.x + line.width / 2) - (x0 + x1) / 2) < 12
    rep = validate_book(b, res, "digital")
    assert any(i.code == "missing_asset" and i.block_id == bad.id for i in rep.issues)


def test_layout_pages_do_not_paint_over_the_chapter_title():
    b = book_with()
    b.sections = [Section("Titlu", "chapter", blocks=[LayoutBlock(layout="photo_full", asset=add_image(b), headline="H")])]
    res = LayoutEngine().build(b)
    title_page = next(p for p in res.pages if any(g.text == "Titlu" for g in glyphs(p)))
    assert not title_page.full_bleed
    assert any(p.full_bleed for p in res.pages if p.index > title_page.index)


# ------------------------------------------------------------------ other formats keep the content
def test_other_formats_keep_the_text_of_boxes_and_layouts(tmp_path):
    b = book_with(language="ro")
    aid = add_image(b)
    b.sections = [Section("C", "chapter", blocks=[
        TextBoxBlock(text="Text din casuta"),
        LayoutBlock(layout="image_left", asset=aid, headline="Titlu pagina", text="Corp de pagina"),
        ImageBlock(asset=aid, place="wrap_left", alt="poza"), ParagraphBlock(runs=[Run("Dupa imagine")])])]
    html = export_other(b, tmp_path / "b.html", "html")
    page = (tmp_path / "b.html").read_text(encoding="utf-8")
    assert "Text din casuta" in page and "Titlu pagina" in page and "Corp de pagina" in page and "Dupa imagine" in page
    export_other(b, tmp_path / "b.epub", "epub")
    assert check_epub(tmp_path / "b.epub") == []
    with zipfile.ZipFile(tmp_path / "b.epub") as z:
        txt = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.startswith("OEBPS/text/section-"))
    assert "Text din casuta" in txt and "Corp de pagina" in txt
    export_other(b, tmp_path / "b.md", "markdown")
    md = (tmp_path / "b.md").read_text(encoding="utf-8")
    assert "Text din casuta" in md and "Corp de pagina" in md
    res = export_other(b, tmp_path / "b.docx", "docx")
    from docx import Document
    d = " ".join(p.text for p in Document(str(tmp_path / "b.docx")).paragraphs)
    assert "Text din casuta" in d and "Corp de pagina" in d
    assert any("Text boxes" in n for n in res.notes) and any("Page layouts" in n for n in res.notes)


def test_blocks_round_trip_through_a_saved_project(tmp_path):
    b = book_with()
    aid = add_image(b)
    blocks = [ImageBlock(asset=aid, place="page", px=0.2, py=0.3, pw=0.4, rotation=5, opacity=0.8),
              TextBoxBlock(text="T", px=0.1, py=0.2, pw=0.3, ph=0.1, color="#123456", background="#EEEEEE"),
              LayoutBlock(layout="quote_page", text="Q", headline="A", size=13)]
    b.sections = [Section("C", "chapter", blocks=blocks)]
    save_project(b, tmp_path / "x.bookforge")
    back = load_project(tmp_path / "x.bookforge").sections[0].blocks
    assert [x.to_dict() for x in back] == [x.to_dict() for x in blocks]


# ------------------------------------------------------------------ dialogs
def test_dialogs_return_what_was_entered(window):
    from app.ui.dialogs.page_setup_dialog import SectionPageDialog, describe_page
    from app.ui.editor.block_dialogs import ImageDialog, LayoutDialog, TextBoxDialog
    st = window.state
    aid = st.project.add_asset(make_png(300, 200), "p.png").id
    d = ImageDialog(window, ImageBlock(asset=aid), st.project)
    d.place.setCurrentIndex(d.place.findData("page"))
    d.px.setValue(25), d.py.setValue(40), d.pw.setValue(33), d.rotation.setValue(-7), d.opacity.setValue(60)
    r = d.result_block()
    assert (r.place, r.px, r.py, r.pw, r.rotation, r.opacity) == ("page", 0.25, 0.4, 0.33, -7.0, 0.6)
    d.place.setCurrentIndex(d.place.findData("wrap_right"))
    assert d.result_block().place == "wrap_right" and not d.px.isEnabled()
    t = TextBoxDialog(window, TextBoxBlock(text="a"))
    t.text.setPlainText("Nou\ntext"), t.pw.setValue(50), t.size_pt.setValue(20), t.bold.setChecked(True)
    t.bg.set_color("#FFEEAA")
    rb = t.result_block()
    assert (rb.text, rb.pw, rb.size, rb.bold, rb.background) == ("Nou\ntext", 0.5, 20.0, True, "#FFEEAA")
    lay = LayoutDialog(window, LayoutBlock(asset=aid), st.project)
    lay.kind.setCurrentIndex(lay.kind.findData("image_top"))
    lay.headline.setText("Cap"), lay.text.setPlainText("Corp"), lay.share.setValue(55)
    lb = lay.result_block()
    assert (lb.layout, lb.headline, lb.text, lb.image_pct, lb.asset) == ("image_top", "Cap", "Corp", 55.0, aid)
    assert not lay.share.isHidden() and not lay.overlay.isVisibleTo(lay)
    sec = Section("S", "chapter")
    sec.page = {"columns": 2, "column_gap_mm": 6, "margins": {"top": 11}}
    pd = SectionPageDialog(window, sec, st.project.settings)
    assert pd.columns.value() == 2 and pd.own_margins.isChecked() and pd.margin["top"].value() == 11
    pd.size_choice.setCurrentIndex(pd.size_choice.findData("A6"))
    pd.columns.setValue(1)
    got = pd.result_page()
    assert got["page_size"] == "A6" and "columns" not in got and got["margins"]["top"] == 11
    pd._reset()
    assert pd.result_page() == {} and describe_page({}) == "Same as the book"
    assert describe_page({"columns": 3, "page_size": "A5", "margins": {"top": 1}}) == "3 columns, own page size, own margins"


def test_section_tab_applies_page_setup_with_undo(window):
    st = window.state
    sid = st.project.sections[-1].id
    window.navigator.select_section(sid) if hasattr(window.navigator, "select_section") else None
    st.set_section_attr(sid, page={"columns": 2})
    assert st.project.find_section(sid).page == {"columns": 2}
    st.undo_stack.undo()
    assert st.project.find_section(sid).page == {}


def test_editor_inserts_and_edits_the_new_blocks(window):
    ed = window.editor
    sec = next(s for s in window.state.project.sections if s.kind == "chapter")
    ed.load_section(sec.id)
    ed.insert_block(TextBoxBlock(text="Caseta"))
    ed.insert_block(LayoutBlock(layout="quote_page", text="Citat"))
    ed.flush()
    kinds = [b.type for b in window.state.project.find_section(sec.id).blocks]
    assert "textbox" in kinds and "page_layout" in kinds
    shown = ed.edit.document().toPlainText()
    assert "[Text box: Caseta]" in shown and "[Page layout: Quote page]" in shown
    labels = [a.text() for a in ed.insert_menu.actions()]
    assert any(l.startswith("Page layout") for l in labels) and any(l.startswith("Text box") for l in labels)


# ------------------------------------------------------------------ preview editing
def _press(canvas, x, y, kind=QMouseEvent.MouseButtonPress):
    ev = QMouseEvent(kind, QPointF(x, y), canvas.mapToGlobal(QPointF(x, y)), Qt.LeftButton, Qt.LeftButton,
                     Qt.NoModifier)
    {QMouseEvent.MouseButtonPress: canvas.mousePressEvent, QMouseEvent.MouseButtonRelease: canvas.mouseReleaseEvent}[kind](ev)


def _move(canvas, x, y):
    ev = QMouseEvent(QMouseEvent.MouseMove, QPointF(x, y), canvas.mapToGlobal(QPointF(x, y)), Qt.NoButton,
                     Qt.LeftButton, Qt.NoModifier)
    canvas.mouseMoveEvent(ev)


@pytest.fixture
def pinned_window(window):
    st = window.state
    aid = st.project.add_asset(make_png(600, 400, (30, 140, 90)), "pic.png").id
    sec = next(s for s in st.project.sections if s.kind == "chapter")
    img = ImageBlock(asset=aid, place="page", px=0.5, py=0.5, pw=0.25)
    box = TextBoxBlock(text="Caseta", px=0.1, py=0.1, pw=0.3, ph=0.1, background="#FFE9A8")
    sec.blocks = [ParagraphBlock(runs=[Run("Text.")]), img, box]
    window.editor.load_section(sec.id)
    st.request_layout(immediate=True)
    assert wait_until(lambda: st.layout is not None and any(
        isinstance(i, ImageItem) for p in st.layout.pages for i in p.items))
    pv = window.preview
    pv.set_layout(st.layout)
    page = next(p for p in st.layout.pages if any(isinstance(i, ImageItem) and i.block_id == img.id for i in p.items))
    pv.show_page(page.index)
    pv.zoom.setCurrentText("100%")
    window.show()
    return window, sec, img, box, page


def _canvas_pos(pv, page, x_pt, y_pt):
    s = pv.scale()
    rect = next(r for p, r in pv.canvas._rects() if p.index == page.index)
    return rect.x() + x_pt * s, rect.y() + y_pt * s


def test_drag_an_image_in_the_preview_moves_it_and_undo_restores(pinned_window):
    window, sec, img, box, page = pinned_window
    pv, st = window.preview, window.state
    item = next(i for i in page.items if isinstance(i, ImageItem) and i.block_id == img.id)
    cx, cy = _canvas_pos(pv, page, item.x + item.w / 2, item.y + item.h / 2)
    s = pv.scale()
    _press(pv.canvas, cx, cy)
    assert pv.canvas.selected == img.id
    _move(pv.canvas, cx + 40 * s, cy + 30 * s)
    _press(pv.canvas, cx + 40 * s, cy + 30 * s, QMouseEvent.MouseButtonRelease)
    blk = next(b for b in st.project.find_section(sec.id).blocks if b.id == img.id)
    assert blk.px == pytest.approx(0.5 + 40 / page.width, abs=0.002) and blk.py == pytest.approx(0.5 + 30 / page.height, abs=0.002)
    assert blk.pw == 0.25  # a move never resizes
    st.undo_stack.undo()
    blk = next(b for b in st.project.find_section(sec.id).blocks if b.id == img.id)
    assert (blk.px, blk.py) == (0.5, 0.5)


def test_drag_the_corner_resizes_a_text_box_and_an_image_keeps_its_aspect(pinned_window):
    window, sec, img, box, page = pinned_window
    pv, st = window.preview, window.state
    s = pv.scale()
    bx, by = _canvas_pos(pv, page, box.px * page.width + 3, box.py * page.height + 3)
    _press(pv.canvas, bx, by)
    _press(pv.canvas, bx, by, QMouseEvent.MouseButtonRelease)  # a click selects it
    assert pv.canvas.selected == box.id
    cx, cy = _canvas_pos(pv, page, (box.px + box.pw) * page.width, (box.py + box.ph) * page.height)
    _press(pv.canvas, cx, cy)
    _move(pv.canvas, cx + 50 * s, cy + 20 * s)
    _press(pv.canvas, cx + 50 * s, cy + 20 * s, QMouseEvent.MouseButtonRelease)
    nb = next(b for b in st.project.find_section(sec.id).blocks if b.id == box.id)
    assert nb.pw == pytest.approx(0.3 + 50 / page.width, abs=0.003) and nb.ph == pytest.approx(0.1 + 20 / page.height, abs=0.003)
    assert (nb.px, nb.py) == (0.1, 0.1)
    # image: only the width follows the mouse, the height keeps the picture's proportions
    item = next(i for i in page.items if isinstance(i, ImageItem) and i.block_id == img.id)
    ix, iy = _canvas_pos(pv, page, item.x + item.w / 2, item.y + item.h / 2)
    _press(pv.canvas, ix, iy)
    _press(pv.canvas, ix, iy, QMouseEvent.MouseButtonRelease)
    hx, hy = _canvas_pos(pv, page, item.x + item.w, item.y + item.h)
    _press(pv.canvas, hx, hy)
    _move(pv.canvas, hx - 30 * s, hy + 90 * s)
    _press(pv.canvas, hx - 30 * s, hy + 90 * s, QMouseEvent.MouseButtonRelease)
    ni = next(b for b in st.project.find_section(sec.id).blocks if b.id == img.id)
    assert ni.pw == pytest.approx(0.25 - 30 / page.width, abs=0.003)


def test_arrow_keys_nudge_the_selected_item_and_escape_deselects(pinned_window):
    window, sec, img, box, page = pinned_window
    pv, st = window.preview, window.state
    pv.canvas.selected = box.id
    QTest.keyClick(pv.canvas, Qt.Key_Right)
    QTest.keyClick(pv.canvas, Qt.Key_Down, Qt.ShiftModifier)
    nb = next(b for b in st.project.find_section(sec.id).blocks if b.id == box.id)
    assert nb.px == pytest.approx(0.1 + 1 / page.width, abs=0.001) and nb.py == pytest.approx(0.1 + 4 / page.height, abs=0.001)
    QTest.keyClick(pv.canvas, Qt.Key_Escape)
    assert pv.canvas.selected is None


def test_editor_keeps_the_dragged_position_when_the_text_is_edited_afterwards(pinned_window):
    window, sec, img, box, page = pinned_window
    pv, st, ed = window.preview, window.state, window.editor
    pv.commit_box(box.id, page, (0.4 * page.width, 0.4 * page.height, 0.3 * page.width, 0.1 * page.height), resized=False)
    from PySide6.QtGui import QTextCursor
    ed.edit.moveCursor(QTextCursor.MoveOperation.Start)
    ed.edit.textCursor().insertText("X")
    ed.flush()
    nb = next(b for b in st.project.find_section(sec.id).blocks if b.id == box.id)
    assert (nb.px, nb.py) == (0.4, 0.4)


# ------------------------------------------------------------------ regressions found by review
def test_page_break_after_a_pinned_item_still_breaks_the_page():
    from app.domain.content_blocks import PageBreakBlock
    sec = Section("C", "chapter", blocks=[TextBoxBlock(text="BOXTEXT"), PageBreakBlock(),
                                         ParagraphBlock(runs=[Run("AFTERBREAK")])])
    sec.show_title = False
    res = LayoutEngine().build(book_with(sec))
    on = {g.text: p.index for p in res.pages for g in glyphs(p)}
    assert on["AFTERBREAK"] > on["BOXTEXT"]


def test_splitting_a_section_keeps_its_page_setup():
    from app.domain.content_blocks import PoetryBlock
    from app.services.section_tools import split_by_poems
    s = Section("P", "chapter", blocks=[PoetryBlock(text="a\nb", title="One"), PoetryBlock(text="c\nd", title="Two")])
    s.page = {"columns": 2}
    new = split_by_poems(book_with(s), s.id)
    assert len(new) == 2 and all(n.page == {"columns": 2} for n in new)
    assert new[0].page is not s.page  # copies, not shared


def test_a_designed_photo_page_at_the_end_is_not_mistaken_for_the_back_cover():
    b = book_with()
    b.settings.page_multiple = 4
    b.sections = [Section("C", "chapter", blocks=paras(1) + [LayoutBlock(layout="photo_full", asset=add_image(b))])]
    res = LayoutEngine().build(b)
    blanks = [p.index for p in res.pages if p.blank]
    assert res.pages[-1].blank or not res.pages[-1].full_bleed  # padding goes after the photo page, not before it
    photo = next(p for p in res.pages if p.full_bleed)
    assert all(i > photo.index for i in blanks)
    cover = Section("Back", "back_cover")
    b.sections.append(cover)
    res = LayoutEngine().build(b)
    assert res.pages[-1].cover == "back" and len(res.pages) % 4 == 0
