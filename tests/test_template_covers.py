import collections

import pymupdf
import pytest

from app.domain.book import BookProject
from app.domain.content_blocks import ParagraphBlock, PoetryBlock, Run
from app.domain.sections import Section
from app.layout.model import Glyphs, RectItem
from app.layout.pagination import LayoutEngine
from app.services.cover_presets import PALETTES, PRESETS, apply_preset
from app.services.export_service import export_pdf
from app.services.project_service import NewBookSpec, create_project
from app.services.screen_edition import SIZES, night_colour, night_layout, screen_edition
from tests.test_ui import qapp, window  # noqa: F401  (fixtures)
from app.services.template_service import TemplateService, apply_template, preview_book, template_from_book

MM = 72 / 25.4
SVC = TemplateService()
TEMPLATES = SVC.list_templates()


def test_every_template_has_its_own_valid_cover():
    pairs = [(t["cover"]["preset"], t["cover"]["palette"]) for t in TEMPLATES]
    assert len(TEMPLATES) >= 33 and len(set(pairs)) == len(pairs), [p for p, n in collections.Counter(pairs).items() if n > 1]
    for t in TEMPLATES:
        assert t["cover"]["preset"] in PRESETS and t["cover"]["palette"] in PALETTES and t["cover"]["font"]


def test_new_book_gets_template_cover_font_and_title_typography():
    for key in ("poetry_nature", "crime_noir", "poetry_love"):
        t = SVC.get(key)
        b = create_project(NewBookSpec(title="T", template=key), SVC)
        cv = b.settings.cover
        assert (cv.preset, cv.palette, cv.from_template) == (t["cover"]["preset"], t["cover"]["palette"], key)
        assert cv.front_layers and all(l.font_family == t["cover"]["font"] for l in cv.front_layers if l.kind == "text")
        assert b.styles["book_title"].font_family == t["cover"]["font"]  # title page speaks the template's font


def test_apply_template_replaces_untouched_cover_but_keeps_a_designed_one():
    b = create_project(NewBookSpec(title="T", template="classic_novel"), SVC)
    apply_template(b, SVC.get("crime_noir"))
    assert b.settings.cover.preset == "ribbon"  # untouched template cover follows the new template
    apply_preset(b, "vintage")  # the author designs their own cover
    b.settings.cover.from_template = ""
    apply_template(b, SVC.get("poetry_love"))
    assert b.settings.cover.preset == "vintage"
    apply_template(b, SVC.get("poetry_love"), apply_cover=True)
    assert b.settings.cover.preset == "horizon"


def test_saved_template_remembers_the_cover():
    b = create_project(NewBookSpec(title="T", template="fantasy_epic"), SVC)
    t = template_from_book(b, "Mine", "mine")
    assert t["cover"]["preset"] == "stars" and t["cover"]["palette"] == "royal"


@pytest.mark.parametrize("key", [t["key"] for t in TEMPLATES])
def test_template_cover_text_fits_and_words_are_not_broken(key):
    b = create_project(NewBookSpec(title="Lumina din Nord, o poveste lunga", author="Ana Popescu", template=key), SVC)
    res = LayoutEngine().build(b)
    cover = res.pages[0]
    shown = " ".join(g.text for g in cover.items if isinstance(g, Glyphs)).lower()
    for w in ("lumina", "din", "nord,", "poveste", "lunga", "ana", "popescu"):
        assert w in shown.split(), (key, w, shown)  # whole words: nothing is broken in the middle
    assert all(0 <= g.x <= cover.width and 0 <= g.y <= cover.height + 2 for g in cover.items if isinstance(g, Glyphs))


def test_preview_book_uses_the_users_text_and_leaves_the_source_alone():
    src = BookProject()
    src.metadata.title, src.metadata.language = "Cartea mea", "ro"
    src.sections = [Section("Poezii", "chapter", blocks=[PoetryBlock(title="Doina", text="un vers\naltul")])]
    pb = preview_book(SVC.get("poetry_love"), src)
    assert [s.kind for s in pb.sections] == ["front_cover", "title_page", "chapter"]
    assert pb.sections[2].blocks[0].title == "Doina" and pb.sections[2].blocks is not src.sections[0].blocks
    assert pb.settings.cover.preset == "horizon" and pb.metadata.title == "Cartea mea"
    assert src.settings.template != "poetry_love" and src.settings.cover.preset == ""
    texts = " ".join(g.text for p in LayoutEngine().build(pb).pages for g in p.items if isinstance(g, Glyphs))
    assert "un vers" in texts
    sample = preview_book(SVC.get("classic_novel"))  # no source: sample text
    assert LayoutEngine().build(sample).page_count >= 3


def test_template_dialog_shows_cover_and_two_pages(window):
    from tests.test_ui import wait_until  # noqa: F401
    from app.ui.dialogs.template_dialog import TemplateDialog
    window.state.project.sections = [Section("Poezii", "chapter", blocks=[
        PoetryBlock(title="A", text="\n".join(f"vers {i}" for i in range(12)))])]
    dlg = TemplateDialog(window.state, window)
    assert all(not l.pixmap().isNull() for l in dlg.pages[:2])  # cover + opening (a 3rd only if text continues)
    dlg.use_mine.setChecked(False)
    assert all(not l.pixmap().isNull() for l in dlg.pages[:2])  # cover + opening (a 3rd only if text continues)
    dlg.close()


def long_book():
    b = BookProject()
    b.sections = [Section("Cap", "chapter", blocks=[ParagraphBlock(runs=[Run("Un paragraf lung. " * 40)])
                                                   for _ in range(14)])]
    return b


@pytest.mark.parametrize("size", list(SIZES))
def test_screen_sizes(tmp_path, size):
    out = tmp_path / f"{size}.pdf"
    export_pdf(long_book(), out, "screen", allow_errors=True, screen_size=size)
    r = pymupdf.open(str(out))[0].rect
    sz = SIZES[size]
    assert abs(r.width - sz.width_mm * MM) < 1 and abs(r.height - sz.height_mm * MM) < 1


def test_night_colours_flip_lightness_and_keep_hue():
    assert night_colour("#000000") != "#000000" and int(night_colour("#000000")[1:3], 16) > 0xD0
    assert int(night_colour("#FFFFFF")[1:3], 16) < 0x30
    assert night_colour("not a colour") == "not a colour" and night_colour(None) is None
    r, g, b = (int(night_colour("#8A3B4A")[i:i + 2], 16) for i in (1, 3, 5))
    assert r > g and r > b  # still reddish


def test_dark_screen_pdf_has_dark_pages_and_light_text(tmp_path):
    book = long_book()
    book.settings.cover.enabled = False
    light, dark = tmp_path / "l.pdf", tmp_path / "d.pdf"
    export_pdf(book, light, "screen", allow_errors=True)
    export_pdf(book, dark, "screen", allow_errors=True, screen_dark=True)
    dl, dd = pymupdf.open(str(light)), pymupdf.open(str(dark))
    assert dl.page_count == dd.page_count
    p = dd[1]
    pix = p.get_pixmap(dpi=40)
    corner = pix.pixel(2, 2)
    assert max(corner) < 60  # dark page
    assert min(dl[1].get_pixmap(dpi=40).pixel(2, 2)) > 230  # the light edition is white
    words = [w for w in p.get_text("words")]
    assert words and "Un" in [w[4] for w in words]  # text is still real, selectable text
    lay = night_layout(LayoutEngine().build(screen_edition(book)))
    assert all(isinstance(pg.items[0], RectItem) for pg in lay.pages if not pg.full_bleed)
