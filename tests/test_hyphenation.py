import statistics

import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, Run
from app.domain.sections import Section
from app.layout.hyphenation import get_hyphenator, split_points
from app.layout.model import Glyphs
from app.layout.pagination import LayoutEngine

RO_TEXT = ("Constantinopolul reprezentativ international extraordinar responsabilitatea "
           "necunoscutul imposibilitatea administrarea întotdeauna disponibilitate ") * 12


def book(hyph: bool, text=RO_TEXT, lang="ro"):
    b = BookProject()
    b.metadata.language = lang
    b.settings.hyphenate = hyph
    b.settings.set_page_size("A6")
    b.sections = [Section("C", "chapter", blocks=[ParagraphBlock(runs=[Run(text)])])]
    return b


def body_lines(res, b):
    bid = b.sections[0].blocks[0].id
    rows = {}
    for pg in res.pages:
        for g in pg.items:
            if isinstance(g, Glyphs) and g.block_id == bid:
                rows.setdefault((pg.index, round(g.y, 1)), []).append(g)
    return [sorted(v, key=lambda g: g.x) for _, v in sorted(rows.items())]


def test_language_dictionaries_and_fallbacks():
    assert get_hyphenator("ro") is not None and get_hyphenator("en-GB") is not None
    assert get_hyphenator("fr_FR") is not None and get_hyphenator("xx") is None and get_hyphenator("") is None
    h = get_hyphenator("ro")
    pts = split_points(h, "Constantinopol")
    assert pts and all(2 <= p <= len("Constantinopol") - 3 for p in pts)
    assert split_points(h, "scurt") == [] and split_points(h, "bine-venit") == []  # short / compound: untouched


def test_off_by_default_and_hyphens_appear_when_on():
    plain = body_lines(LayoutEngine().build(book(False)), book(False))
    assert not any(ln[-1].text.endswith("-") for ln in plain)
    b = book(True)
    res = LayoutEngine().build(b)
    lines = body_lines(res, b)
    hyphenated = [ln for ln in lines if ln[-1].text.endswith("-")]
    assert len(hyphenated) >= 5


def test_hyphenation_never_loses_or_alters_text_and_lines_fit():
    b = book(True)
    res = LayoutEngine().build(b)
    lines = body_lines(res, b)
    joined = ""
    for ln in lines:
        text = "".join(g.text for g in ln)
        joined += text[:-1] if text.endswith("-") else text + " "
    assert joined.split() == RO_TEXT.split()  # re-joining the split words restores the manuscript exactly
    page = res.pages[0]
    x0, _, x1, _ = page.content_box
    for ln in lines:
        assert ln[-1].x + ln[-1].width <= max(p.content_box[2] for p in res.pages) + 0.6


def test_hyphenation_evens_out_justified_spacing():
    def spacing(b):
        res = LayoutEngine().build(b)
        return statistics.mean(g.word_space for ln in body_lines(res, b)[:-1] for g in ln if g.word_space)
    assert spacing(book(True)) < spacing(book(False))


def test_unsupported_language_falls_back_to_no_hyphenation():
    b = book(True, lang="xx")
    lines = body_lines(LayoutEngine().build(b), b)
    assert not any(ln[-1].text.endswith("-") for ln in lines)


def test_hyphenated_pdf_text_is_selectable_and_complete(tmp_path):
    import pymupdf
    from app.services.export_service import export_pdf
    b = book(True)
    dest = tmp_path / "h.pdf"
    export_pdf(b, dest, "digital", allow_errors=True)
    text = "\n".join(p.get_text() for p in pymupdf.open(str(dest)))
    flat = text.replace("-\n", "").replace("\n", " ")
    assert RO_TEXT.split()[0] in flat and flat.count("Constantinopolul") == 12
