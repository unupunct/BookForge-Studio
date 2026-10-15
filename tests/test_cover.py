"""Layered cover designer: presets, palettes, art tools, exports and the editor dialog."""
import io

import pymupdf
import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from app.domain.book import BookProject
from app.domain.layouts import MM_TO_PT, CoverDesign, CoverLayer
from app.layout.cover_builder import PATTERNS, layer_items, resolve_tokens
from app.layout.model import Glyphs, ImageItem, LineItem, RectItem
from app.layout.page_builder import cover_items
from app.persistence.project_archive import load_project, save_project
from app.services.cover_presets import PALETTES, PRESETS, apply_palette, apply_preset
from app.services.cover_service import (CoverExportError, build_cover_layout, export_cover_pdf,
                                        spine_width_mm)
from app.services.image_service import apply_fx, prepare_image
from app.ui.dialogs.cover_editor import CoverDialog
from tests.conftest import make_png
from tests.test_ui import chapter, qapp, wait_until, window  # noqa: F401  (fixtures)


def cover_book() -> BookProject:
    b = BookProject()
    b.metadata.title, b.metadata.subtitle, b.metadata.author = "Școala de vară", "Povești", "Ion Țăranu"
    b.settings.cover.back_text = "Text de pe coperta a patra."
    b.add_asset(make_png(600, 900, (30, 90, 160)), "photo.png")
    return b


def texts(items):
    return [i.text for i in items if isinstance(i, Glyphs)]


@pytest.mark.parametrize("key", list(PRESETS))
def test_every_preset_renders_front_and_back(key):
    b = cover_book()
    apply_preset(b, key)
    W, H = b.settings.page_size_pt()
    front = cover_items(b, W, H, False)
    back = cover_items(b, W, H, True)
    assert "".join(texts(front)).replace(" ", "").upper().count("ȘCOALA") + \
        "".join(texts(front)).replace(" ", "").upper().count("ŞCOALA") >= 1 or \
        any("OALA" in t.upper() for t in texts(front))
    assert any("Ion" in t or "ION" in t for t in texts(front))
    assert any("coperta" in t for t in texts(back))
    assert isinstance(front[0], RectItem) and front[0].w == W and front[0].h == H  # background first
    for it in front:
        if isinstance(it, Glyphs):
            assert it.x >= -1 and it.x + it.width <= W + 1, (key, it.text)  # text stays on the cover


def test_tokens_follow_metadata_changes():
    b = cover_book()
    apply_preset(b, "classic")
    W, H = b.settings.page_size_pt()
    b.metadata.title = "Alt titlu"
    assert any("Alt" in t for t in texts(cover_items(b, W, H, False)))
    assert resolve_tokens("{title} / {author}", b) == "Alt titlu / Ion Țăranu"


def test_palette_recolours_by_role():
    b = cover_book()
    apply_preset(b, "classic")
    apply_palette(b, "forest")
    cv = b.settings.cover
    label, bg, bg2, title, sub, author, accent = PALETTES["forest"]
    assert cv.background == bg
    assert next(l for l in cv.front_layers if l.role == "title").color == title
    assert next(l for l in cv.front_layers if l.role == "author").color == author
    assert next(l for l in cv.front_layers if l.kind == "frame").stroke == accent


def test_all_pattern_kinds_generate_bounded_items():
    b = cover_book()
    for pat in PATTERNS:
        L = CoverLayer("pattern", x=0, y=0, w=1, h=1, pattern=pat, scale=4, fill="#FFFFFF")
        items = layer_items(b, L, 420, 595)
        assert 0 < len(items) <= 4200, (pat, len(items))
        assert all(getattr(i, "opacity", 1) == 1 for i in items)


def test_shapes_rotation_opacity_and_text_fit():
    b = cover_book()
    W, H = 420.0, 595.0
    ell = layer_items(b, CoverLayer("ellipse", x=.2, y=.2, w=.4, h=.2, rotation=30, opacity=.5), W, H)[0]
    assert ell.shape == "ellipse" and ell.rot == 30 and ell.opacity == .5
    assert (ell.pivot_x, ell.pivot_y) == pytest.approx((W * .4, H * .3))
    long = CoverLayer("text", text="A very long title that needs to shrink " * 3, x=.1, y=.1, w=.8, h=.15, size=60,
                      autofit=True, color="#fff")
    gs = [g for g in layer_items(b, long, W, H) if isinstance(g, Glyphs)]
    assert max(g.size for g in gs) < 60
    ys = [g.y for g in gs]
    assert max(ys) <= H * (.1 + .15) + 6  # stays inside its box
    shadowed = layer_items(b, CoverLayer("text", text="Hi", shadow=True, x=.1, y=.1, w=.8, h=.1), W, H)
    assert len(texts(shadowed)) == 2 and shadowed[0].opacity < shadowed[1].opacity
    hidden = layer_items(b, CoverLayer("rect", visible=False), W, H)
    assert hidden == []


def test_image_layer_cover_fit_does_not_distort_and_missing_image():
    b = cover_book()
    a = next(iter(b.assets.values()))
    W, H = 420.0, 595.0
    it = layer_items(b, CoverLayer("image", asset=a.id, x=0, y=0, w=1, h=.5, fit="cover"), W, H)[0]
    assert isinstance(it, ImageItem)
    l, t, r, bt = it.crop
    src_aspect = (a.width * (r - l)) / (a.height * (bt - t))
    assert src_aspect == pytest.approx(it.w / it.h, rel=0.02)  # crop matches the box: no stretching
    cont = layer_items(b, CoverLayer("image", asset=a.id, x=0, y=0, w=1, h=.5, fit="contain"), W, H)[0]
    assert cont.w / cont.h == pytest.approx(a.width / a.height, rel=0.02)
    gone = layer_items(b, CoverLayer("image", asset="nope", x=0, y=0, w=1, h=1), W, H)[0]
    assert isinstance(gone, RectItem) and gone.stroke  # flagged, not silently dropped


def test_image_filters_change_pixels_but_never_the_stored_asset():
    b = cover_book()
    a = next(iter(b.assets.values()))
    before = bytes(a.data)
    gray = apply_fx(Image.open(io.BytesIO(a.data)).convert("RGB"), {"grayscale": True})
    r, g, bl = gray.getpixel((5, 5))
    assert r == g == bl
    sepia = apply_fx(Image.open(io.BytesIO(a.data)).convert("RGB"), {"sepia": True}).getpixel((5, 5))
    assert sepia[0] > sepia[2]
    dark = apply_fx(Image.open(io.BytesIO(a.data)).convert("RGB"), {"brightness": 0.4}).getpixel((5, 5))
    assert sum(dark) < sum(Image.open(io.BytesIO(a.data)).convert("RGB").getpixel((5, 5)))
    flipped = apply_fx(Image.new("RGB", (4, 1)), None, True)
    assert flipped.size == (4, 1)
    wash = apply_fx(Image.new("RGB", (2, 2), (0, 0, 0)), {"tint": "#FFFFFF", "tint_alpha": 0.5}).getpixel((0, 0))
    assert 120 <= wash[0] <= 135
    data, fmt = prepare_image(a, None, 200, 150, 80, (("grayscale", True),), False)
    assert Image.open(io.BytesIO(data)).convert("RGB").getpixel((3, 3))[0] == Image.open(io.BytesIO(data)).convert("RGB").getpixel((3, 3))[2]
    assert a.data == before


def test_cover_layers_survive_save_and_reopen(tmp_path):
    b = cover_book()
    apply_preset(b, "geometric")
    b.settings.cover.front_layers[0].fx = {"sepia": True}
    p = tmp_path / "c.bookforge"
    save_project(b, p)
    again = load_project(p)
    assert again.settings.cover.to_dict() == b.settings.cover.to_dict()
    assert again.settings.cover.front_layers[1].kind == "ellipse"
    assert again.settings.cover.preset == "geometric"


def test_legacy_projects_without_layers_still_build_a_cover():
    b = cover_book()
    cv = CoverDesign.from_dict({"background": "#112233", "title_size": 30})
    b.settings.cover = cv
    W, H = b.settings.page_size_pt()
    items = cover_items(b, W, H, False)
    assert items[0].fill == "#112233" and any("oala" in t for t in texts(items))


def test_spine_width_is_an_estimate_from_pages_and_user_thickness():
    assert spine_width_mm(200, 0.1) == pytest.approx(10.0)
    assert spine_width_mm(0, 0.1) == 0
    assert spine_width_mm(101, 0.12) == pytest.approx(6.06)


def test_export_front_back_and_wrap_pdfs(tmp_path):
    b = cover_book()
    apply_preset(b, "classic")
    W, H = b.settings.page_size_pt()
    front = export_cover_pdf(b, tmp_path / "front.pdf", "front", "digital")
    d = pymupdf.open(str(front))
    assert d.page_count == 1 and d[0].rect.width == pytest.approx(W, abs=0.6)
    assert "Școala" in d[0].get_text() or "coala" in d[0].get_text()
    both = export_cover_pdf(b, tmp_path / "both.pdf", "front_back", "print", crop_marks=True)
    d = pymupdf.open(str(both))
    ofs = 3 * MM_TO_PT + 9 * MM_TO_PT
    assert d.page_count == 2 and d[0].rect.width == pytest.approx(W + 2 * ofs, abs=0.6)
    assert d[0].trimbox.width == pytest.approx(W, abs=0.6)
    wrap = export_cover_pdf(b, tmp_path / "wrap.pdf", "wrap", "print", spine_mm=12.5, crop_marks=False)
    d = pymupdf.open(str(wrap))
    bleed = 3 * MM_TO_PT
    assert d.page_count == 1
    assert d[0].rect.width == pytest.approx(2 * W + 12.5 * MM_TO_PT + 2 * bleed, abs=0.8)
    assert d[0].rect.height == pytest.approx(H + 2 * bleed, abs=0.8)
    # spine text is rotated: its line direction is vertical
    lines = [ln for blk in d[0].get_text("dict")["blocks"] if blk["type"] == 0 for ln in blk["lines"]]
    rotated = [ln for ln in lines if abs(ln["dir"][0]) < 0.1 and abs(ln["dir"][1]) > 0.9]
    assert rotated and any("coala" in "".join(s["text"] for s in ln["spans"]) for ln in rotated)
    with pytest.raises(CoverExportError):
        export_cover_pdf(b, tmp_path / "wrap.pdf", "wrap", "print", 12.5)
    with pytest.raises(CoverExportError):
        export_cover_pdf(b, tmp_path / "nope" / "x.pdf", "front")
    assert not list(tmp_path.glob(".*.tmp"))


def test_wrap_layout_geometry_and_back_text_position():
    b = cover_book()
    apply_preset(b, "modern")
    W, H = b.settings.page_size_pt()
    lay = build_cover_layout(b, "wrap", 10.0)
    assert lay.page_width == pytest.approx(2 * W + 10 * MM_TO_PT)
    spine_x0 = W
    front_texts = [i for i in lay.pages[0].items if isinstance(i, Glyphs) and "oala" in i.text.lower() and not i.rot]
    assert front_texts and all(i.x >= W + 10 * MM_TO_PT - 1 for i in front_texts)  # front sits right of spine
    back_texts = [i for i in lay.pages[0].items if isinstance(i, Glyphs) and "coperta" in i.text]
    assert back_texts and all(i.x < W for i in back_texts)


# ------------------------------------------------------------- the dialog
def test_cover_dialog_materialises_layers_and_edits(window, monkeypatch, tmp_path):
    state = window.state
    state.project.settings.cover.image_asset = ""
    dlg = CoverDialog(state, window)
    kinds = [l.kind for l in dlg.design.front_layers]
    assert kinds.count("text") >= 3 and dlg.layer_list.count() == len(kinds)
    dlg.add_layer("ellipse")
    dlg.add_layer("pattern")
    assert dlg.current_layer().kind == "pattern"
    dlg.pattern.setCurrentText("dots")
    dlg._set(pattern="dots")
    assert dlg.current_layer().pattern == "dots"
    dlg.opacity.setValue(40)
    assert dlg.current_layer().opacity == pytest.approx(0.4)
    dlg.move_layer(-1)
    dlg.duplicate_layer()
    n = len(dlg.design.front_layers)
    dlg.delete_layer()
    assert len(dlg.design.front_layers) == n - 1
    # switch to the back cover and edit its text layer
    dlg.side_btn.setChecked(True)
    dlg._toggle_side()
    assert dlg.side == "back" and dlg.layer_list.count() >= 2
    dlg.layer_list.setCurrentRow(dlg.layer_list.count() - 1)
    assert dlg.current_layer().kind == "text"
    # accept → stored in the project, undoable
    dlg._ok()
    cv = state.project.settings.cover
    assert any(l.kind == "pattern" for l in cv.front_layers) and cv.back_layers
    state.undo_stack.undo()
    assert not any(l.kind == "pattern" for l in state.project.settings.cover.front_layers)


def test_cover_dialog_preset_palette_and_canvas_drag(window, monkeypatch):
    state = window.state
    state.project.metadata.title = "Titlu"
    dlg = CoverDialog(state, window)
    dlg.show()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    dlg.preset.setCurrentIndex(dlg.preset.findData("vintage"))
    dlg._preset_chosen(0)
    assert dlg.design.preset == "vintage" and dlg.design.background == "#E8DCC0"
    dlg.palette.setCurrentIndex(dlg.palette.findData("ocean"))
    dlg._palette_chosen(0)
    assert dlg.design.background == PALETTES["ocean"][1]
    title_row = next(i for i, l in enumerate(reversed(dlg.design.front_layers)) if l.role == "title")
    dlg.layer_list.setCurrentRow(title_row)
    L = dlg.current_layer()
    x0, y0 = L.x, L.y
    s, ox, oy = dlg.canvas._geometry()
    W, H = dlg.book.settings.page_size_pt()
    start = QPoint(int(ox + (L.x + L.w / 2) * W * s), int(oy + (L.y + L.h / 2) * H * s))
    QTest.mousePress(dlg.canvas, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(dlg.canvas, start + QPoint(30, 40))
    QTest.mouseRelease(dlg.canvas, Qt.LeftButton, Qt.NoModifier, start + QPoint(30, 40))
    assert L.x > x0 and L.y > y0  # dragging moved the layer
    dlg.canvas.setFocus()
    before = L.x
    QTest.keyClick(dlg.canvas, Qt.Key_Left)
    assert L.x < before
    dlg.close()


def test_cover_dialog_exports(window, tmp_path, monkeypatch):
    state = window.state
    dlg = CoverDialog(state, window)
    png = tmp_path / "front.png"
    assert dlg.export_png(str(png), dpi=100)
    img = Image.open(png)
    W, H = state.project.settings.page_size_pt()
    assert img.size[0] == pytest.approx(W / 72 * 100, abs=2)
    state.project.settings.bleed_mm = 3.0
    out = tmp_path / "wrap.pdf"
    assert dlg._export_pdf("wrap", "print", str(out))
    assert pymupdf.open(str(out)).page_count == 1
    dlg.close()
