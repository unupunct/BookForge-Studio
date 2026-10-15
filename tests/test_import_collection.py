"""Exported collections (one post per poem): header / poem / hashtag / separator repeated."""
import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from app.domain.content_blocks import ParagraphBlock, PoetryBlock
from app.importers.base import ImportOptions
from app.layout.model import Glyphs
from app.layout.pagination import LayoutEngine
from app.services.import_service import run_import
from app.services.project_service import NewBookSpec, create_from_manuscript
from app.services.validation_service import validate_book

KEEP = ImportOptions(header_lines="keep", signature_lines="keep")
LINES = ["Câte am greșit", "și câte voi mai greși.", "Probabil că viața", "nu mă va lăsa niciodată",
         "fără o greșeală nouă"]


def collection_docx(path, n=6, long_every=3, with_title_block=True, page_break=True, author="python-docx"):
    d = Document()
    d.core_properties.author = author
    if with_title_block:
        for text, bold, italic in (("COLECȚIE DE TEST", True, False), ("Postările mele", False, True),
                                   (f"{n} postări distincte", True, False)):
            p = d.add_paragraph()
            r = p.add_run(text)
            r.bold, r.italic = bold, italic
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        d.add_paragraph("")
    if page_break:
        d.add_page_break()
    for i in range(1, n + 1):
        head = d.add_paragraph()
        a = head.add_run(f"{i}. ")
        b = head.add_run(f"Oct {i:02d}, 2026 12:52:33 pm")
        a.bold = b.bold = True
        body = d.add_paragraph()
        lines = LINES * (12 if i % long_every == 0 else 1)
        for k, line in enumerate(lines):
            run = body.add_run(f"{line} {i}")
            if k < len(lines) - 1:
                run.add_break()
        tag = d.add_paragraph()
        t = tag.add_run("#unupunctpoezie")
        t.italic = True
        tag.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        sep = d.add_paragraph("—")
        sep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.save(path)


def poems(res):
    return [b for s in res.sections for b in s.blocks if isinstance(b, PoetryBlock)]


def test_every_post_becomes_its_own_poem(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    res = run_import(f, ImportOptions(header_lines="keep", signature_lines="keep")).result
    ps = poems(res)
    assert len(ps) == 6  # not one giant poem
    assert ps[0].title == "1. Oct 01, 2026 12:52:33 pm"
    assert ps[0].text.split("\n") == [f"{l} 1" for l in LINES]
    assert len(ps[2].text.split("\n")) == len(LINES) * 12
    assert all(p.signature == "#unupunctpoezie" for p in ps)  # hashtag travels with its poem
    assert not any(isinstance(b, ParagraphBlock) for s in res.sections for b in s.blocks)
    msgs = " ".join(i.message for i in res.report.issues)
    assert "separator line" in msgs and "signature" in msgs and "poem(s) recognised" in msgs


def test_title_block_becomes_metadata_not_body(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    res = run_import(f, ImportOptions()).result
    assert res.title == "COLECȚIE DE TEST" and res.subtitle == "Postările mele"
    assert res.description == "6 postări distincte"
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_free_verse"),
                                  run_import(f, ImportOptions()), ImportOptions())
    assert book.metadata.title == "COLECȚIE DE TEST" and book.metadata.subtitle == "Postările mele"
    assert book.metadata.author == ""  # "python-docx" is a tool name, not an author
    chapter = [s for s in book.sections if s.kind == "chapter"]
    assert len(chapter) == 1 and chapter[0].show_title is False  # title page already names the book
    first = chapter[0].blocks[0]
    assert isinstance(first, PoetryBlock)  # the leading page break did not survive


def test_header_policy_number_and_drop(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    num = poems(run_import(f, ImportOptions(header_lines="number")).result)
    assert [p.title for p in num] == ["1", "2", "3", "4", "5", "6"]
    gone = poems(run_import(f, ImportOptions(header_lines="drop")).result)
    assert all(p.title == "" for p in gone)
    kept = poems(run_import(f, ImportOptions(header_lines="keep")).result)
    assert kept[3].title.startswith("4. Oct")


def test_signature_policy_drop(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    res = run_import(f, ImportOptions(signature_lines="drop")).result
    assert all(p.signature == "" for p in poems(res))
    assert any("signature line(s) were removed" in i.message for i in res.report.issues)


def test_generic_author_ignored_real_author_kept(tmp_path):
    f = tmp_path / "a.docx"
    collection_docx(f, author="Ion Creangă")
    assert run_import(f).result.author == "Ion Creangă"
    collection_docx(f, author="python-docx")
    assert run_import(f).result.author is None


def test_signature_prints_right_aligned_with_the_poem_and_titles_stay_with_text(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f, n=14)
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_free_verse"),
                                  run_import(f, KEEP), KEEP)
    res = LayoutEngine().build(book)
    ps = [b for s in book.sections for b in s.blocks if isinstance(b, PoetryBlock)]
    for p in ps:
        pages = res.block_pages[p.id]
        last = res.pages[pages[-1]]
        glyphs = [g for g in last.items if isinstance(g, Glyphs) and g.block_id == p.id]
        sig = [g for g in glyphs if g.text == "#unupunctpoezie"]
        assert sig, "signature must be printed"
        x0, _, x1, _ = last.content_box
        assert sig[0].x + sig[0].width == pytest.approx(x1, abs=1.5)  # right-aligned
        rows = {round(g.y, 1) for g in glyphs}
        assert len(rows) >= 3, f"signature alone on page {pages[-1]}"  # never orphaned
        # the poem's title is never stranded at the bottom of a page: text follows on the same page
        first = res.pages[pages[0]]
        g0 = [g for g in first.items if isinstance(g, Glyphs) and g.block_id == p.id]
        assert len({round(g.y, 1) for g in g0}) >= 3
    assert not [i for i in res.issues if i.severity in ("error", "warning")]


def test_validation_summarises_repeated_layout_notes(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f, n=14, long_every=1)  # every poem runs onto another page
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_free_verse"),
                                  run_import(f, ImportOptions()), ImportOptions())
    rep = validate_book(book, LayoutEngine().build(book))
    cont = [i for i in rep.issues if i.code == "poem_continues"]
    assert len(cont) == 1 and "×" in cont[0].message  # one summary line instead of dozens


def test_ordinary_bold_line_in_prose_is_not_a_poem(tmp_path):
    f = tmp_path / "p.docx"
    d = Document()
    d.add_heading("Capitolul 1", 1)
    d.add_paragraph("Text lung. " * 40)
    p = d.add_paragraph()
    p.add_run("Un subtitlu aldin").bold = True
    d.add_paragraph("Alt text lung. " * 40)
    d.save(f)
    blocks = run_import(f).result.sections[0].blocks
    assert not any(isinstance(b, PoetryBlock) for b in blocks)
    assert len(blocks) == 3 and blocks[1].plain_text() == "Un subtitlu aldin"


def test_defaults_give_a_clean_book_number_titles_and_no_boilerplate_hashtag(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    res = run_import(f).result  # default options
    ps = poems(res)
    assert [p.title for p in ps] == ["1", "2", "3", "4", "5", "6"]
    assert all(p.signature == "" for p in ps)  # the same hashtag closed every post: boilerplate
    msgs = " ".join(i.message for i in res.report.issues)
    assert "same line closed every post" in msgs and "numbered date headers were shortened" in msgs


def test_unique_signatures_are_kept_by_default(tmp_path):
    f = tmp_path / "u.docx"
    d = Document()
    d.add_heading("Poeme", 1)
    for name in ("Ana", "Ion", "Maria"):
        for line in LINES:
            d.add_paragraph(f"{line} {name}")
        sig = d.add_paragraph(f"\u2014 {name}")
        sig.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        d.add_paragraph("")
        d.add_paragraph("")
        d.add_paragraph("")
    d.save(f)
    ps = poems(run_import(f).result)
    assert [p.signature for p in ps] == ["\u2014 Ana", "\u2014 Ion", "\u2014 Maria"]  # distinct lines are content


def test_poem_number_never_stranded_even_when_title_plus_poem_exceeds_a_page(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f, n=40, long_every=1)
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_ballad_epic"),
                                  run_import(f, ImportOptions()), ImportOptions())
    res = LayoutEngine().build(book)
    for p in [b for s in book.sections for b in s.blocks if isinstance(b, PoetryBlock)]:
        for pg in res.block_pages[p.id]:
            rows = {round(g.y, 1) for g in res.pages[pg].items if isinstance(g, Glyphs) and g.block_id == p.id}
            assert len(rows) >= 3, f"poem {p.title} has a lone line on page {pg}"


def test_no_blank_copyright_page_when_there_is_nothing_to_print(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f)
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_ballad_epic"),
                                  run_import(f, ImportOptions()), ImportOptions())
    assert not next(s for s in book.sections if s.kind == "copyright").enabled
    res = LayoutEngine().build(book)
    # the only blank left is the leaf facing the first poem: the template opens chapters on right-hand pages
    blanks = [p.index for p in res.pages if p.blank]
    assert blanks == [1, 3] and not [i for i in res.issues if i.code == "accidental_blank_page"]


def test_every_poem_on_its_own_page_tightens_slight_overflow_and_keeps_all_text(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f, n=12, long_every=2)
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_ballad_epic"),
                                  run_import(f, ImportOptions()), ImportOptions())
    book.settings.poems_new_page = True
    res = LayoutEngine().build(book)
    ps = [b for s in book.sections for b in s.blocks if isinstance(b, PoetryBlock)]
    owner = {}
    for p in ps:
        for pg in res.block_pages[p.id]:
            assert owner.setdefault(pg, p.id) == p.id  # a page never holds two poems
    assert len({res.block_pages[p.id][0] for p in ps}) == len(ps)
    for p in ps:  # a continuation page carries at least 4 lines (widow rule for own-page poems)
        pages = res.block_pages[p.id]
        if len(pages) > 1:
            rows = {round(g.y, 1) for g in res.pages[pages[-1]].items
                    if isinstance(g, Glyphs) and g.block_id == p.id and g.text != "(continued)"}
            assert len(rows) >= 4
    words = [g.text for pg in res.pages for g in pg.items if isinstance(g, Glyphs)]
    assert sum(w.count("Câte") for w in words) >= 12 * 1  # nothing lost


def test_slightly_too_tall_poem_is_tightened_onto_one_page(tmp_path):
    from app.domain.book import BookProject
    from app.domain.sections import Section
    b = BookProject()
    b.settings.poems_new_page = True
    probe = PoetryBlock(text="\n".join(f"verse {i}" for i in range(10)))
    b.sections = [Section("P", "chapter", blocks=[probe])]
    one = LayoutEngine().build(b)
    # find a line count that overflows at normal spacing but fits when tightened
    for n in range(30, 80):
        poem = PoetryBlock(text="\n".join(f"verse {i}" for i in range(n)))
        b.sections = [Section("P", "chapter", blocks=[poem])]
        res = LayoutEngine().build(b)
        if len(res.block_pages[poem.id]) == 1:
            last_single = n
        else:
            break
    assert last_single >= 30
    b.settings.line_height = 1.8
    b.styles["poetry"].line_height = 1.8
    sizes = []
    for n in (last_single, last_single + 2):
        poem = PoetryBlock(text="\n".join(f"verse {i}" for i in range(n)))
        b.sections = [Section("P", "chapter", blocks=[poem])]
        res = LayoutEngine().build(b)
        sizes.append(len(res.block_pages[poem.id]))
    assert sizes[0] == 1  # tightening let a poem that overflows at 1.8 leading fit on one page
