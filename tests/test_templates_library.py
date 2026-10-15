"""The 20 new novel/poetry templates (plus the originals) must all produce sound books."""
import json

import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, PoetryBlock, Run
from app.domain.sections import Section
from app.layout.model import Glyphs
from app.layout.page_builder import BuildContext
from app.layout.pagination import LayoutEngine
from app.layout.typography import fonts
from app.services.template_service import TemplateService, apply_template
from tests.conftest import LOREM, RO

SVC = TemplateService()
ALL = SVC.list_templates()
NOVELS = [t for t in ALL if t["key"] in {
    "literary_fiction", "thriller_paperback", "romance_soft", "fantasy_epic", "historical_saga",
    "young_adult", "crime_noir", "scifi_modern", "massmarket_classic", "elegant_hardcover"}]
POETRY = [t for t in ALL if t["key"].startswith("poetry_")]
POEM = "\n".join(["Pe un picior de plai,", "Pe-o gură de rai,", "", "Iată vine o mioară,",
                  "Mioară bârsană,", "", "Pe-un picior de plai"])


def novel_book(tpl):
    b = BookProject()
    b.metadata.title, b.metadata.author = "Cartea", "Autor"
    apply_template(b, tpl, preserve_customised_styles=False)
    b.sections = [Section("Title page", "title_page", show_title=False), Section("Contents", "toc", in_toc=False)]
    for i in range(3):
        b.sections.append(Section(f"Capitolul {i + 1}", "chapter", blocks=[
            ParagraphBlock(runs=[Run(LOREM * 9 + RO)]) for _ in range(8)]))
    return b


def poetry_book(tpl):
    b = BookProject()
    b.metadata.title, b.metadata.author = "Versuri", "Poet"
    apply_template(b, tpl, preserve_customised_styles=False)
    b.sections = [Section("Title page", "title_page", show_title=False), Section("Contents", "toc", in_toc=False),
                  Section("Prima parte", "chapter", blocks=[
                      PoetryBlock(title="Mioriţa", text=POEM), PoetryBlock(title="Doina", text=POEM)])]
    return b


def test_counts():
    assert len(NOVELS) == 10 and len(POETRY) >= 10
    assert len({t["key"] for t in ALL}) == len(ALL) >= 33


@pytest.mark.parametrize("tpl", NOVELS + POETRY, ids=lambda t: t["key"])
def test_template_fonts_cover_romanian(tpl):
    b = BookProject()
    apply_template(b, tpl, preserve_customised_styles=False)
    ctx = BuildContext(b)
    families = {ctx.style(n).font_family for n in ("body", "chapter_title", "chapter_label", "poetry",
                                                   "poetry_title", "header_footer", "toc_entry")}
    for fam in families:
        assert fonts.missing_glyphs(fam, "ĂÂÎȘȚăâîșț„”—…") == set(), (tpl["key"], fam)


@pytest.mark.parametrize("tpl", NOVELS, ids=lambda t: t["key"])
def test_novel_template_layout_style(tpl):
    b = novel_book(tpl)
    res = LayoutEngine().build(b)
    st = tpl["settings"]
    ch1 = b.sections[2]
    page = res.pages[res.section_pages[ch1.id]]
    assert page.opening and page.matter == "main"
    assert not [i for i in res.issues if i.severity in ("error", "warning")], res.issues
    assert abs(res.page_width - st["width_mm"] * 72 / 25.4) < 0.5
    m = st["margins"]
    inner = (m["inner"]) * 72 / 25.4
    outer = m["outer"] * 72 / 25.4
    xs = {round(p.content_box[0], 1) for p in res.pages if not p.full_bleed}
    assert xs <= {round(inner, 1), round(outer, 1)}
    texts = [g.text for g in page.items if isinstance(g, Glyphs)]
    if st.get("chapter_number_style", "none") != "none":
        label = st.get("chapter_label", "Chapter {n}").replace("{n}", "I" if st.get("chapter_number_style", "none") == "roman" else "1")
        shown = " ".join(texts)
        assert label in shown or label.upper() in shown.upper(), (label, texts[:6])
    first_y = min(g.y for g in page.items if isinstance(g, Glyphs))
    assert first_y > page.content_box[1] + st.get("chapter_drop", 60) * 0.8
    first_main = res.section_pages[ch1.id]
    assert res.pages[first_main].label == "1"
    if st.get("footer_position", "center") != "none":
        assert any(isinstance(d, Glyphs) and "1" in d.text for d in res.pages[first_main].decorations)
    if st.get("chapter_right_page", False):
        assert page.side == "recto"


@pytest.mark.parametrize("tpl", POETRY, ids=lambda t: t["key"])
def test_poetry_template_layout_style(tpl):
    b = poetry_book(tpl)
    res = LayoutEngine().build(b)
    assert not [i for i in res.issues if i.severity in ("error", "warning")], res.issues
    st = tpl["settings"]
    poems = list(b.sections[2].blocks)
    pg0, pg1 = res.block_pages[poems[0].id][0], res.block_pages[poems[1].id][0]
    if st.get("poems_new_page"):
        assert pg0 != pg1  # one poem per page
    page = res.pages[pg0]
    lines = {}
    for g in page.items:
        if isinstance(g, Glyphs) and g.block_id == poems[0].id:
            lines.setdefault(round(g.y, 1), []).append(g)
    ys = sorted(lines)
    body_ys = ys[1:]  # the first row is the poem title
    assert len(body_ys) == 5  # no line merged or lost
    step = body_ys[1] - body_ys[0]
    gap = body_ys[2] - body_ys[1]
    assert gap == pytest.approx(step * (1 + st.get("stanza_gap", 0.9)), rel=0.03)
    x0, _, x1, _ = page.content_box
    firsts = [min(g.x for g in lines[y]) for y in body_ys]
    if tpl["styles"]["poetry"].get("align") == "center":
        for y in body_ys:
            gs = lines[y]
            left, right = min(g.x for g in gs), max(g.x + g.width for g in gs)
            assert (left + right) / 2 == pytest.approx((x0 + x1) / 2, abs=2.0)
    else:
        assert len({round(f, 1) for f in firsts[:2]}) == 1
        assert firsts[0] == pytest.approx(x0 + tpl["styles"]["poetry"].get("left_indent", 0), abs=1.0)


def test_templates_are_visually_distinct():
    sigs = set()
    for t in NOVELS + POETRY:
        s = t["settings"]
        sigs.add((s["body_font"], s["width_mm"], s["height_mm"], s["body_size"], s.get("chapter_ornament"),
                  s.get("chapter_number_style"), s.get("stanza_gap"), json.dumps(t["styles"], sort_keys=True)))
    assert len(sigs) == len(NOVELS + POETRY)


def test_chapter_numbering_ornament_and_drop_mechanics():
    b = BookProject()
    b.settings.chapter_number_style = "roman"
    b.settings.chapter_label = "Capitolul {n}"
    b.settings.chapter_ornament = "stars"
    b.settings.chapter_drop = 100
    b.sections = [Section("Început", "chapter", blocks=[ParagraphBlock(runs=[Run("x " * 30)])]),
                  Section("Urmare", "chapter", blocks=[ParagraphBlock(runs=[Run("y " * 30)])])]
    res = LayoutEngine().build(b)
    p1 = res.pages[res.section_pages[b.sections[0].id]]
    texts = [g.text for g in p1.items if isinstance(g, Glyphs)]
    assert "Capitolul I" in texts and "Început" in texts and any("*" in t for t in texts)
    p2 = res.pages[res.section_pages[b.sections[1].id]]
    assert any(isinstance(g, Glyphs) and g.text == "Capitolul II" for g in p2.items)
    ys = [g.y for g in p1.items if isinstance(g, Glyphs)]
    assert min(ys) > p1.content_box[1] + 100
    b.settings.chapter_number_style = "none"
    res2 = LayoutEngine().build(b)
    assert not any(isinstance(g, Glyphs) and g.text.startswith("Capitolul") for p in res2.pages for g in p.items)
