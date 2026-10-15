from collections import defaultdict

import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import (CodeBlock, HeadingBlock, ImageBlock, PageBreakBlock,
                                       ParagraphBlock, PoetryBlock, Run, TableBlock)
from app.domain.layouts import MM_TO_PT
from app.domain.sections import Section
from app.layout.model import Glyphs, ImageItem
from app.layout.pagination import LayoutEngine, to_roman
from app.layout.typography import fonts
from tests.conftest import LOREM, RO, make_png


def layout(book):
    return LayoutEngine().build(book)


def body_pages(res, section_title_prefix=None):
    return [p for p in res.pages if p.items]


def words(res):
    out = []
    for p in res.pages:
        for it in p.items:
            if isinstance(it, Glyphs):
                out.extend(it.text.split())
    return out


def lines_by_block(page):
    """Distinct baselines per block on a page."""
    d = defaultdict(set)
    for it in page.items:
        if isinstance(it, Glyphs) and it.block_id:
            d[it.block_id].add(round(it.y, 1))
    return d


def book_with(blocks, title="Ch", settings=None, kind="chapter"):
    b = BookProject()
    if settings:
        for k, v in settings.items():
            setattr(b.settings, k, v)
    b.sections = [Section(title, kind, blocks=blocks)]
    return b


# ---------------------------------------------------------------- basics
def test_roman():
    assert [to_roman(i) for i in (1, 4, 9, 14, 40)] == ["i", "iv", "ix", "xiv", "xl"]


def test_chapters_start_on_new_pages(sample_book):
    res = layout(sample_book)
    for ch in [s for s in sample_book.sections if s.kind == "chapter"]:
        pg = res.pages[res.section_pages[ch.id]]
        assert pg.opening
        first = min((it.y for it in pg.items if isinstance(it, Glyphs)), default=None)
        assert first is not None and first < pg.content_box[1] + 200
    starts = [res.section_pages[s.id] for s in sample_book.sections if s.kind == "chapter"]
    assert len(set(starts)) == len(starts)


def test_chapter_right_page_inserts_intentional_blank():
    b = BookProject()
    b.settings.chapter_right_page = True
    b.sections = [Section("A", "chapter", blocks=[ParagraphBlock(runs=[Run("one")])]),
                  Section("B", "chapter", blocks=[ParagraphBlock(runs=[Run("two")])])]
    res = layout(b)
    assert res.pages[res.section_pages[b.sections[1].id]].side == "recto"
    assert [p.blank for p in res.pages] == [None, "intentional", None]
    assert not [i for i in res.issues if i.code == "accidental_blank_page"]
    assert res.pages[1].label == "" and res.pages[2].label == "3"


def test_mirrored_margins():
    b = book_with([ParagraphBlock(runs=[Run(LOREM * 30)])] * 1)
    b.settings.margins.inner, b.settings.margins.outer = 25.0, 12.0
    res = layout(b)
    rec = next(p for p in res.pages if p.side == "recto")
    ver = next(p for p in res.pages if p.side == "verso")
    assert rec.content_box[0] == pytest.approx(25 * MM_TO_PT)
    assert rec.content_box[2] == pytest.approx(rec.width - 12 * MM_TO_PT)
    assert ver.content_box[0] == pytest.approx(12 * MM_TO_PT)
    assert ver.content_box[2] == pytest.approx(ver.width - 25 * MM_TO_PT)
    b.settings.mirrored_margins = False
    res2 = layout(b)
    assert all(p.content_box[0] == pytest.approx(25 * MM_TO_PT) for p in res2.pages)


def test_gutter_adds_to_inner_margin():
    b = book_with([ParagraphBlock(runs=[Run("x")])])
    b.settings.gutter_mm = 5
    res = layout(b)
    assert res.pages[0].content_box[0] == pytest.approx((b.settings.margins.inner + 5) * MM_TO_PT)


def test_text_stays_inside_content_box_and_nothing_is_lost(sample_book):
    res = layout(sample_book)
    for p in res.pages:
        x0, y0, x1, y1 = p.content_box
        for it in p.items:
            if isinstance(it, Glyphs):
                assert it.x >= x0 - 0.5 and it.x + it.width <= x1 + 0.5, (p.index, it.text)
                assert it.y <= y1 + 0.5
    expected = []
    for s in sample_book.sections:
        for blk in s.blocks:
            if isinstance(blk, (ParagraphBlock, HeadingBlock)):
                expected.extend(blk.plain_text().split())
    got = words(res)
    # every manuscript word appears in the layout, in order
    it = iter(got)
    assert all(any(w == g for g in it) for w in expected)


def test_long_paragraph_splits_with_widow_orphan_control():
    b = book_with([ParagraphBlock(runs=[Run(LOREM * 60)]) for _ in range(3)])
    res = layout(b)
    assert res.page_count >= 3
    for p in res.pages:
        for bid, ys in lines_by_block(p).items():
            total_pages = res.block_pages[bid]
            if len(total_pages) > 1:
                assert len(ys) >= 2, "orphan/widow: a single line left on a page"


def test_long_heading_wraps_and_stays_with_next():
    long = "A very long heading that must wrap across several lines of the page " * 3
    blocks = [ParagraphBlock(runs=[Run(LOREM * 14)]), HeadingBlock(level=1, runs=[Run(long)]),
              ParagraphBlock(runs=[Run(LOREM * 3)])]
    b = book_with(blocks)
    res = layout(b)
    head_id = blocks[1].id
    pages = res.block_pages[head_id]
    assert len(pages) == 1
    ys = lines_by_block(res.pages[pages[0]])[head_id]
    assert len(ys) >= 2
    # the following paragraph starts on the same page as the heading
    assert res.block_pages[blocks[2].id][0] == pages[0]


def test_keep_with_next_moves_heading_to_next_page():
    filler = ParagraphBlock(runs=[Run(LOREM * 12)])
    head = HeadingBlock(level=1, runs=[Run("Heading")])
    follow = ParagraphBlock(runs=[Run(LOREM * 6)])
    # find a filler count that leaves the heading near the page bottom
    for n in range(1, 8):
        blocks = [ParagraphBlock(runs=[Run(LOREM * 12)]) for _ in range(n)] + [head, follow]
        res = layout(book_with(blocks))
        hp = res.block_pages[head.id][0]
        assert hp == res.block_pages[follow.id][0], "heading separated from its paragraph"


def test_large_image_is_scaled_with_warning_not_distorted(png_bytes):
    b = BookProject()
    big = b.add_asset(make_png(300, 3000), "tall.png")
    b.sections = [Section("Img", "chapter", blocks=[ImageBlock(asset=big.id, width_pct=100)])]
    res = layout(b)
    items = [it for p in res.pages for it in p.items if isinstance(it, ImageItem)]
    assert len(items) == 1
    it = items[0]
    page = res.pages[res.block_pages[it.block_id][0]]
    x0, y0, x1, y1 = page.content_box
    assert it.y >= y0 - 0.1 and it.y + it.h <= y1 + 0.1 and it.w <= x1 - x0 + 0.1
    assert it.h / it.w == pytest.approx(10.0, rel=0.01)  # aspect preserved
    assert any(i.code == "image_scaled" for i in res.issues)


def test_image_kept_with_caption_and_missing_asset_reported():
    b = BookProject()
    a = b.add_asset(make_png(400, 300), "a.png")
    blocks = [ParagraphBlock(runs=[Run(LOREM * 10)]),
              ImageBlock(asset=a.id, caption=[Run("Caption text")]),
              ImageBlock(asset="nope", caption=[Run("Missing one")])]
    b.sections = [Section("Img", "chapter", blocks=blocks)]
    res = layout(b)
    cap_page = next(p for p in res.pages for it in p.items
                    if isinstance(it, Glyphs) and "Caption" in it.text)
    assert any(isinstance(it, ImageItem) and it.asset_id == a.id for it in cap_page.items)
    assert any(i.code == "missing_asset" for i in res.issues)


def test_table_splits_by_rows_with_repeated_header():
    rows = [["Header A", "Header B"]] + [[f"row {i}", f"value {i}"] for i in range(80)]
    b = book_with([TableBlock(rows=rows, header_rows=1)])
    res = layout(b)
    assert res.page_count >= 2
    for p in res.pages[:2]:
        texts = [it.text for it in p.items if isinstance(it, Glyphs)]
        assert any("Header A" in t for t in texts), "header row not repeated"
    all_text = " ".join(it.text for p in res.pages for it in p.items if isinstance(it, Glyphs))
    assert "row 79" in all_text and "row 0" in all_text


def test_oversized_table_row_reported_as_overflow():
    huge = " ".join(["word"] * 3000)
    b = book_with([TableBlock(rows=[["h", "h"], [huge, "x"]], header_rows=1)])
    res = layout(b)
    assert any(i.code == "overflow" and i.severity == "error" for i in res.issues)


def test_poetry_preserves_lines_and_stanzas():
    text = "Line A\nLine B  with spaces\n\nStanza two line\nlast"
    blk = PoetryBlock(text=text, title="Poem")
    res = layout(book_with([blk]))
    p = res.pages[res.block_pages[blk.id][0]]
    glyphs = [it for it in p.items if isinstance(it, Glyphs) and it.block_id == blk.id]
    ys = sorted({round(g.y, 1) for g in glyphs})
    # title + 4 lines; each source line sits on its own baseline
    assert len(ys) == 5
    by_y = defaultdict(str)
    for g in sorted(glyphs, key=lambda g: g.x):
        by_y[round(g.y, 1)] += g.text
    assert list(by_y.values())[1:] == ["Line A", "Line B with spaces", "Stanza two line", "last"]
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert gaps[2] > gaps[1] * 1.3  # stanza break is larger than line spacing


def test_poetry_one_per_page_and_continuation():
    a = PoetryBlock(text="one\ntwo", title="A", one_per_page=True)
    b_ = PoetryBlock(text="three\nfour", title="B", one_per_page=True)
    res = layout(book_with([a, b_]))
    assert res.block_pages[a.id] != res.block_pages[b_.id]
    long = PoetryBlock(text="\n".join(f"verse line number {i}" for i in range(120)), title="Epic")
    res2 = layout(book_with([long]))
    assert len(res2.block_pages[long.id]) >= 2
    assert any(i.code == "poem_continues" for i in res2.issues)
    cont = [it for it in res2.pages[res2.block_pages[long.id][1]].items
            if isinstance(it, Glyphs) and it.text == "(continued)"]
    assert cont
    txt = " ".join(it.text for p in res2.pages for it in p.items if isinstance(it, Glyphs))
    assert "verse line number 0" in txt and "verse line number 119" in txt


def test_code_block_loses_no_characters_when_wrapped():
    code = "def f():\n    x = '" + "ab" * 150 + "'\n\treturn x  # trailing"
    blk = CodeBlock(text=code)
    res = layout(book_with([blk]))
    got = "".join(it.text for p in res.pages for it in p.items
                  if isinstance(it, Glyphs) and it.kind == "code")
    assert got.replace(" ", "") == code.expandtabs(4).replace("\n", "").replace(" ", "")
    assert any(i.code == "code_wrapped" for i in res.issues)
    assert "    x = '" in "".join(it.text for p in res.pages for it in p.items
                                   if isinstance(it, Glyphs) and it.kind == "code")


def test_page_breaks_intentional_vs_redundant():
    b = book_with([ParagraphBlock(runs=[Run("a")]), PageBreakBlock(), PageBreakBlock(),
                   ParagraphBlock(runs=[Run("b")]), PageBreakBlock(blank=True),
                   ParagraphBlock(runs=[Run("c")])])
    b.settings.facing_pages = False
    res = layout(b)
    assert [p.blank for p in res.pages] == [None, None, "intentional", None]
    assert not [i for i in res.issues if i.code == "accidental_blank_page"]


def test_page_numbering_roman_front_arabic_main(sample_book):
    res = layout(sample_book)
    labels = [p.label for p in res.pages]
    first_main = res.section_pages[sample_book.sections[2].id]
    # title page, intentional blank verso (unnumbered but counted), TOC on the next recto
    assert labels[:3] == ["i", "", "iii"]
    assert labels[first_main] == "1"
    assert labels[first_main + 1] == "2"
    footer = [d for d in res.pages[first_main].decorations if isinstance(d, Glyphs) and d.kind == "header" and d.text == "1"]
    assert footer, "page number is printed in the footer"


def test_running_headers_suppressed_on_chapter_openings(sample_book):
    res = layout(sample_book)
    ch = sample_book.sections[2]
    opening = res.pages[res.section_pages[ch.id]]
    texts = [d.text for d in opening.decorations if isinstance(d, Glyphs)]
    assert ch.title not in texts
    later = res.pages[res.section_pages[ch.id] + 1]
    assert any(isinstance(d, Glyphs) and d.text in (ch.title, sample_book.metadata.title)
               for d in later.decorations)


def test_toc_pages_match_headings(sample_book):
    res = layout(sample_book)
    toc_page = res.pages[res.section_pages[sample_book.sections[1].id]]
    toc_text = {}
    for it in toc_page.items:
        if isinstance(it, Glyphs) and it.link:
            toc_text.setdefault(it.link, []).append(it.text)
    for ch in [s for s in sample_book.sections if s.kind == "chapter"]:
        link = f"#sec:{ch.id}"
        assert link in toc_text
        label = res.pages[res.section_pages[ch.id]].label
        assert label in toc_text[link]
    assert any(e.title == "Secțiunea 1" for e in res.outline)


def test_romanian_glyphs_available_in_all_logical_fonts():
    for fam in ("serif", "sans", "mono"):
        assert fonts.missing_glyphs(fam, "ĂÂÎȘȚăâîșț„”—…") == set(), fam


def test_front_matter_has_independent_margins():
    b = BookProject()
    b.settings.matter_margins = {"front": {"top": 40.0}}
    b.sections = [Section("Title", "title_page", show_title=False),
                  Section("Ch", "chapter", blocks=[ParagraphBlock(runs=[Run("x")])])]
    res = layout(b)
    front = res.pages[0]
    main = res.pages[res.section_pages[b.sections[1].id]]
    assert front.content_box[1] == pytest.approx(40 * MM_TO_PT)
    assert main.content_box[1] == pytest.approx(b.settings.margins.top * MM_TO_PT)


def test_cover_is_full_bleed_and_unnumbered():
    b = BookProject()
    b.metadata.title = "Cover test"
    b.sections = [Section("c", "front_cover"),
                  Section("Ch", "chapter", blocks=[ParagraphBlock(runs=[Run("x")])]),
                  Section("bc", "back_cover")]
    res = layout(b)
    assert res.pages[0].full_bleed and res.pages[0].label == ""
    assert res.pages[-1].full_bleed
    assert not res.pages[0].decorations


def test_flow_cache_reuses_unchanged_sections(sample_book):
    eng = LayoutEngine()
    eng.build(sample_book)
    size = len(eng._cache)
    sample_book.sections[3].blocks[0].runs = [Run("changed " * 20)]
    eng.build(sample_book)
    assert len(eng._cache) <= size + 1  # only the edited section was re-measured


def test_large_manuscript_layout_performance():
    import time
    b = BookProject()
    for i in range(120):
        b.sections.append(Section(f"Chapter {i}", "chapter",
                                  blocks=[ParagraphBlock(runs=[Run(LOREM * 6)]) for _ in range(25)]))
    t = time.perf_counter()
    res = LayoutEngine().build(b)
    elapsed = time.perf_counter() - t
    assert res.page_count > 300
    assert elapsed < 20, f"layout of {res.page_count} pages took {elapsed:.1f}s"
