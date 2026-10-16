import pymupdf

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, Run
from app.domain.sections import Section
from app.services.export_service import export_pdf
from app.services.screen_edition import SCREEN_HEIGHT_MM, SCREEN_WIDTH_MM, screen_edition

MM = 72 / 25.4


def print_book():
    b = BookProject()
    s = b.settings
    s.page_size, s.width_mm, s.height_mm = "A5", 148, 210
    s.facing_pages = s.mirrored_margins = s.chapter_right_page = True
    s.page_multiple, s.gutter_mm, s.body_size = 8, 6.0, 9.0
    b.sections = [Section("Cap", "chapter", blocks=[ParagraphBlock(runs=[Run("Un paragraf lung. " * 40)])
                                                   for _ in range(12)])]
    return b


def test_screen_edition_does_not_touch_the_book():
    b = print_book()
    ed = screen_edition(b)
    assert ed is not b and ed.sections[0].blocks is b.sections[0].blocks  # blocks shared, sections copied
    assert (b.settings.width_mm, b.settings.page_multiple, b.settings.facing_pages) == (148, 8, True)
    st = ed.settings
    assert (st.width_mm, st.height_mm) == (SCREEN_WIDTH_MM, SCREEN_HEIGHT_MM)
    assert not st.facing_pages and not st.mirrored_margins and st.page_multiple == 0
    assert st.gutter_mm == 0 and st.body_size >= 11 and st.hyphenate


def test_screen_pdf_is_phone_sized_and_not_print_prepared(tmp_path):
    b = print_book()
    scr, prn = tmp_path / "s.pdf", tmp_path / "p.pdf"
    res = export_pdf(b, scr, "screen", allow_errors=True)
    export_pdf(b, prn, "print", allow_errors=True)
    doc = pymupdf.open(str(scr))
    r = doc[0].rect
    assert abs(r.width - SCREEN_WIDTH_MM * MM) < 1 and abs(r.height - SCREEN_HEIGHT_MM * MM) < 1  # no bleed, no marks
    assert res.pages == doc.page_count and doc.page_count > 1
    assert pymupdf.open(str(prn)).page_count % 8 == 0  # print is padded, screen is not
    text = " ".join(p.get_text() for p in doc)
    assert "Un paragraf lung." in text
    words = [w for w in doc[1].get_text("words")]
    assert min(w[0] for w in words) >= 8 * MM - 1 and max(w[2] for w in words) <= r.width - 8 * MM + 1
