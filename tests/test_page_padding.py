import pytest
import pymupdf

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, Run
from app.domain.sections import Section
from app.layout.pagination import LayoutEngine
from app.services.export_service import export_pdf
from app.services.validation_service import validate_book
from tests.conftest import LOREM


def book(n_paragraphs, multiple, cover=True):
    b = BookProject()
    b.metadata.title = "Pad"
    b.settings.page_multiple = multiple
    secs = []
    if cover:
        secs.append(Section("Front", "front_cover", in_toc=False))
    secs.append(Section("C", "chapter", blocks=[ParagraphBlock(runs=[Run(LOREM * 8)]) for _ in range(n_paragraphs)]))
    if cover:
        secs.append(Section("Back", "back_cover", in_toc=False))
    b.sections = secs
    return b


@pytest.mark.parametrize("multiple", [2, 4, 8, 16, 32])
def test_page_count_becomes_a_multiple_with_back_cover_last(multiple):
    for n in (3, 9, 14, 21):
        b = book(n, multiple)
        res = LayoutEngine().build(b)
        assert res.page_count % multiple == 0, (multiple, n, res.page_count)
        assert res.pages[-1].full_bleed and res.pages[0].full_bleed  # the covers stay first and last
        blanks = [p for p in res.pages if p.blank]
        assert all(p.blank == "intentional" for p in blanks)
        assert not [i for i in res.issues if i.code == "accidental_blank_page"]


def test_off_by_default_and_no_extra_pages_when_already_a_multiple():
    base = LayoutEngine().build(book(9, 0))
    assert not any(i.code == "pages_padded" for i in base.issues)
    n = base.page_count
    exact = LayoutEngine().build(book(9, n)) if n > 1 else base
    assert exact.page_count == n and not any(i.code == "pages_padded" for i in exact.issues)


def test_padding_without_cover_and_note_and_pdf(tmp_path):
    b = book(5, 4, cover=False)
    res = LayoutEngine().build(b)
    assert res.page_count % 4 == 0
    note = next(i for i in res.issues if i.code == "pages_padded") if res.page_count != LayoutEngine().build(book(5, 0, False)).page_count else None
    dest = tmp_path / "p.pdf"
    r = export_pdf(b, dest, "print", allow_errors=True)
    assert pymupdf.open(str(dest)).page_count == r.pages == res.page_count
    assert validate_book(b, res).ok


def test_labels_ignore_the_padding_pages():
    b = book(9, 8)
    res = LayoutEngine().build(b)
    labelled = [p.label for p in res.pages if p.label]
    assert labelled == [str(i) for i in range(1, len(labelled) + 1)]  # blank leaves are unnumbered, no gaps
