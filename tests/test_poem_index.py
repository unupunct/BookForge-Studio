import pymupdf

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, PoetryBlock, Run
from app.domain.sections import Section
from app.importers.base import ImportOptions
from app.layout.model import Glyphs
from app.layout.pagination import LayoutEngine
from app.services.export_service import export_pdf
from app.services.import_service import run_import
from app.services.project_service import NewBookSpec, create_from_manuscript
from tests.test_import_collection import collection_docx


def poetry_book(mode):
    b = BookProject()
    b.metadata.title, b.metadata.author = "Versuri", "Poet"
    b.settings.poem_index = mode
    poems = [PoetryBlock(title=t, text="\n".join(f"{first} {i}" if k == 0 else f"linie {k}" for k in range(30)))
             for i, (t, first) in enumerate([("1", "Primul vers"), ("Toamna", "Frunze cad"), ("3", "Ploaie de vară")])]
    b.sections = [Section("Contents", "toc", in_toc=False),
                  Section("Poeme", "chapter", blocks=poems)]
    return b, poems


def index_rows(res, toc_section_id):
    page = res.pages[res.section_pages[toc_section_id]]
    rows = {}
    for g in page.items:
        if isinstance(g, Glyphs):
            rows.setdefault(round(g.y, 1), []).append(g)
    return [sorted(r, key=lambda g: g.x) for _, r in sorted(rows.items())]


def test_titles_mode_lists_every_poem_with_correct_page_numbers():
    b, poems = poetry_book("titles")
    res = LayoutEngine().build(b)
    rows = index_rows(res, b.sections[0].id)
    texts = ["".join(g.text for g in r if g.color != "#777777") for r in rows]
    assert any("Index of poems" in t for t in texts)
    joined = "\n".join(texts)
    assert "1. Primul vers 0" in joined and "Toamna" in joined and "3. Ploaie de vară 2" in joined
    for p in poems:
        link = f"#blk:{p.id}"
        entry = [g for r in rows for g in r if g.link == link]
        assert entry, p.title
        label = res.pages[res.block_pages[p.id][0]].label
        assert label in [g.text for g in entry]  # the printed number is the real page


def test_first_lines_mode_and_none():
    b, poems = poetry_book("first_lines")
    res = LayoutEngine().build(b)
    joined = "\n".join("".join(g.text for g in r) for r in index_rows(res, b.sections[0].id))
    assert "Frunze cad 1" in joined and "Toamna" not in joined
    b2, _ = poetry_book("none")
    res2 = LayoutEngine().build(b2)
    assert "Index of poems" not in "\n".join("".join(g.text for g in r) for r in index_rows(res2, b2.sections[0].id))


def test_index_links_work_in_the_pdf(tmp_path):
    b, poems = poetry_book("titles")
    dest = tmp_path / "p.pdf"
    export_pdf(b, dest, "digital")
    doc = pymupdf.open(str(dest))
    res = LayoutEngine().build(b)
    toc_page = res.section_pages[b.sections[0].id]
    targets = {l["page"] for l in doc[toc_page].get_links() if l["kind"] == pymupdf.LINK_GOTO}
    for p in poems:
        assert res.block_pages[p.id][0] in targets


def test_collection_import_adds_contents_with_poem_list(tmp_path):
    f = tmp_path / "c.docx"
    collection_docx(f, n=12)
    book = create_from_manuscript(NewBookSpec(profile="poetry", template="poetry_ballad_epic"),
                                  run_import(f, ImportOptions()), ImportOptions())
    assert book.settings.poem_index == "titles" and any(s.kind == "toc" for s in book.sections)
    kinds = [s.kind for s in book.sections]
    assert kinds.index("toc") < kinds.index("chapter")
    res = LayoutEngine().build(book)
    assert not [i for i in res.issues if i.severity in ("error", "warning")]
    toc = next(s for s in book.sections if s.kind == "toc")
    shown = "\n".join("".join(g.text for g in r) for r in index_rows(res, toc.id))
    assert "1. Câte am greșit 1" in shown and "12. Câte am greșit 12" in shown
    chapter = next(s for s in book.sections if s.kind == "chapter")
    assert chapter.show_title is False
    assert f"sec:{chapter.id}" not in shown  # the unnamed chapter is not listed
