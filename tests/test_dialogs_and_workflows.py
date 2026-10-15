"""Dialogs and complete specialised-book workflows (cookbook, textbook, children's, cover)."""
import pymupdf
import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from app.domain.book import BookProject
from app.domain.content_blocks import (ExerciseBlock, ImageBlock, ParagraphBlock, QuoteBlock,
                                       RecipeBlock, Run, runs_text)
from app.domain.sections import Section
from app.layout.model import Glyphs, ImageItem
from app.layout.pagination import LayoutEngine
from app.services.export_service import export_pdf
from app.services.project_service import NewBookSpec
from app.ui.dialogs.misc_dialogs import CoverDialog, ValidationDialog
from app.ui.dialogs.template_dialog import TemplateDialog
from app.ui.editor.block_dialogs import ImageDialog, RecipeDialog, TableDialog, choose_and_add_image
from tests.conftest import RO, make_png
from tests.test_ui import chapter, insert_text, qapp, wait_until, window  # noqa: F401  (fixtures)


def test_image_insert_dialog_crop_and_caption(window, tmp_path, monkeypatch):
    img = tmp_path / "photo.png"
    img.write_bytes(make_png(800, 400, (30, 90, 200)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(img), "")))
    window.editor.insert_image()
    window.state.flush()
    blk = next(b for b in chapter(window).blocks if isinstance(b, ImageBlock))
    asset = window.state.project.assets[blk.asset]
    assert asset.width == 800 and blk.width_pct == window.state.project.settings.image_default_width_pct
    dlg = ImageDialog(window, blk, window.state.project)
    dlg.caption.setText("Un apus de soare")
    dlg.alt.setText("Cer albastru")
    dlg.width.setValue(60)
    dlg.crop[0].setValue(10)
    dlg.own_page.setChecked(True)
    new = dlg.result_block()
    assert runs_text(new.caption) == "Un apus de soare" and new.alt == "Cer albastru"
    assert new.width_pct == 60 and new.own_page and new.crop == pytest.approx([0.1, 0, 1, 1])
    assert new.id == blk.id and new.asset == blk.asset
    dlg.close()


def test_image_file_that_is_not_an_image_is_rejected(window, tmp_path, monkeypatch):
    bad = tmp_path / "fake.png"
    bad.write_bytes(b"this is not an image")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(bad), "")))
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2])))
    assert choose_and_add_image(window, window.state.project) is None
    assert warned and not window.state.project.assets


def test_table_dialog_edit(window):
    from app.domain.content_blocks import TableBlock
    dlg = TableDialog(window, TableBlock(rows=[["Nume", "Preț"], ["Pâine", "5"]], header_rows=1))
    dlg._add_row()
    dlg._add_col()
    dlg.table.item(2, 0).setText("Lapte")
    dlg.table.item(2, 1).setText("7")
    dlg.align.setCurrentText("right")
    res = dlg.result_block()
    assert res.rows[:2] == [["Nume", "Preț", ""], ["Pâine", "5", ""]]
    assert res.rows[2][:2] == ["Lapte", "7"] and res.align == ["right"] * 3
    dlg._del_row()
    dlg._del_col()
    assert len(dlg.result_block().rows) == 2 and len(dlg.result_block().rows[0]) == 2
    dlg.close()


def test_cookbook_workflow_to_pdf(window, tmp_path):
    state = window.state
    state.new_project(NewBookSpec(title="Rețete de acasă", author="Bunica", profile="cookbook"))
    dlg = RecipeDialog(window, RecipeBlock(), state.project)
    dlg.title.setText("Ciorbă de perișoare")
    dlg.prep.setText("30 min")
    dlg.cook.setText("45 min")
    dlg.serv.setText("6")
    dlg.ingr.setPlainText("500 g carne tocată\n1 ceapă\n2 morcovi")
    dlg.steps.setPlainText("Se amestecă carnea.\nSe fierbe supa.")
    dlg.nutr.setText("")
    block = dlg.result_block()
    dlg.close()
    ch = next(s for s in state.project.sections if s.kind == "chapter")
    ch.blocks = [block]
    dest = tmp_path / "cookbook.pdf"
    res = export_pdf(state.project.snapshot(), dest, "digital", allow_errors=True)
    text = "\n".join(p.get_text() for p in pymupdf.open(str(dest)))
    for frag in ("Ciorbă de perișoare", "Prep: 30 min", "Cook: 45 min", "Serves: 6", "500 g carne tocată",
                 "Ingredients", "Method", "Se fierbe supa."):
        assert frag in text, frag
    assert "Nutrition" not in text  # never invented


def test_textbook_workflow_exercise_blocks(window, tmp_path, monkeypatch):
    state = window.state
    state.new_project(NewBookSpec(title="Fizică", profile="textbook"))
    window.navigator.rebuild()
    ch = next(s for s in state.project.sections if s.kind == "chapter")
    window.navigator.select(ch.id)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Viteza", True)))
    window.editor.insert_exercise("definition")
    window.editor.edit.textCursor().insertText("Raportul dintre distanță și timp.")
    state.flush()
    ex = [b for b in ch.blocks if isinstance(b, ExerciseBlock)]
    assert any(e.kind == "definition" and e.title == "Viteza" and "distanță" in runs_text(e.runs) for e in ex)
    dest = tmp_path / "tb.pdf"
    export_pdf(state.project.snapshot(), dest, "digital", allow_errors=True)
    text = "\n".join(p.get_text() for p in pymupdf.open(str(dest)))
    assert "Definition: Viteza" in text and "Raportul dintre distanță și timp." in text
    assert "Learning objective: Learning objectives" in text


def test_children_book_full_page_illustration():
    b = BookProject()
    a = b.add_asset(make_png(600, 400, (255, 200, 0)), "sun.png")
    b.settings.page_size = "Custom"
    b.settings.width_mm = b.settings.height_mm = 203
    b.sections = [Section("Story", "chapter", blocks=[
        ParagraphBlock(runs=[Run("Once upon a time.")]),
        ImageBlock(asset=a.id, width_pct=100, own_page=True, alt="A sun"),
        ParagraphBlock(runs=[Run("The end.")])])]
    res = LayoutEngine().build(b)
    img_page = next(p for p in res.pages if any(isinstance(i, ImageItem) for i in p.items))
    texts = [i.text for i in img_page.items if isinstance(i, Glyphs)]
    assert texts == [] or all("Once" not in t and "end" not in t for t in texts)
    assert res.block_pages[b.sections[0].blocks[0].id] != res.block_pages[b.sections[0].blocks[1].id]
    assert res.block_pages[b.sections[0].blocks[2].id][0] > res.block_pages[b.sections[0].blocks[1].id][0]
    it = next(i for i in img_page.items if isinstance(i, ImageItem))
    x0, y0, x1, y1 = img_page.content_box
    assert it.y > y0  # vertically centred on the dedicated page


def test_quote_and_scene_break_layout():
    b = BookProject()
    b.sections = [Section("Ch", "chapter", blocks=[
        ParagraphBlock(runs=[Run("Before.")]),
        QuoteBlock(runs=[Run("Ce frumos!")], attribution=[Run("Cineva")]),
        ParagraphBlock(runs=[Run("After.")])])]
    res = LayoutEngine().build(b)
    words = [i.text for p in res.pages for i in p.items if isinstance(i, Glyphs)]
    assert any("Ce frumos!" in w for w in words) and any("Cineva" in w for w in words)


def test_cover_dialog_changes_and_exports_png(window, tmp_path, monkeypatch):
    state = window.state
    dlg = CoverDialog(state, window)
    dlg.design.background = "#123456"
    dlg.family.setCurrentText("sans")
    dlg.t_size.setValue(44)
    dlg.back.setPlainText("Un text pe coperta a patra.")
    dlg._update()
    assert not dlg.preview.pixmap().isNull()
    png = tmp_path / "cover.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(png), "")))
    dlg._export_png()
    img = QImage(str(png))
    assert not img.isNull() and img.width() > 1000
    dlg._ok()
    cv = state.project.settings.cover
    assert cv.background == "#123456" and cv.title_size == 44 and cv.font_family == "sans"
    assert "patra" in cv.back_text
    state.undo_stack.undo()
    assert state.project.settings.cover.background != "#123456"


def test_cover_dialog_warns_about_low_resolution_image(window, monkeypatch):
    state = window.state
    asset = state.project.add_asset(make_png(300, 400), "lowres.png")
    state.project.settings.cover.image_asset = asset.id
    dlg = CoverDialog(state, window)
    assert "below 300 dpi" in dlg.dpi_note.text()
    state.project.settings.cover.image_asset = ""
    dlg.close()


def test_template_dialog_apply_duplicate_preview(window, monkeypatch):
    state = window.state
    dlg = TemplateDialog(state, window)
    assert dlg.list.count() >= 13
    assert dlg.preview.pixmap() is not None and not dlg.preview.pixmap().isNull()
    keys = [dlg.list.item(i).data(0x100) for i in range(dlg.list.count())]
    dlg.list.setCurrentRow(keys.index("technical_handbook"))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    dlg._apply()
    assert state.project.settings.template == "technical_handbook"
    state.undo_stack.undo()
    assert state.project.settings.template != "technical_handbook"
    dlg2 = TemplateDialog(state, window)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Al meu stil", True)))
    dlg2._duplicate()
    assert any(dlg2.list.item(i).text().startswith("Al meu stil") for i in range(dlg2.list.count()))
    dlg.close()
    dlg2.close()


def test_template_application_does_not_clobber_content(window):
    state = window.state
    insert_text(window, "Textul meu rămâne")
    state.flush()
    before = [b.plain_text() for s in state.project.sections for b in s.blocks]
    from app.services.template_service import apply_template
    state.edit("tpl", lambda p: apply_template(p, state.templates.get("photo_heavy")), kind="settings")
    assert [b.plain_text() for s in state.project.sections for b in s.blocks] == before


def test_block_tab_poetry_and_heading_properties(window):
    from app.domain.content_blocks import HeadingBlock, PageBreakBlock, PoetryBlock
    from app.layout.pagination import LayoutEngine
    state, ed = window.state, window.editor
    ch = chapter(window)
    poem1 = PoetryBlock(text="one\ntwo", title="")
    poem2 = PoetryBlock(text="three\nfour")
    head = HeadingBlock(level=1, runs=[Run("Secțiune")])
    ch.blocks = [poem1, poem2, head, PageBreakBlock()]
    ed.load_section(ch.id)
    bt = window.properties.block_tab
    assert ed.scroll_to_block(poem1.id)
    bt.refresh()
    assert not bt.one_page.isHidden() and bt.h_toc.isHidden()
    bt.one_page.setChecked(True)
    bt.poem_title.setText("Primul poem")
    bt.poem_title.editingFinished.emit()
    state.flush()
    first = next(b for b in ch.blocks if isinstance(b, PoetryBlock))
    assert first.one_per_page is True and first.title == "Primul poem" and first.text == "one\ntwo"
    res = LayoutEngine().build(state.project)
    p1 = [b for b in ch.blocks if isinstance(b, PoetryBlock)]
    assert res.block_pages[p1[0].id][0] != res.block_pages[p1[1].id][0]
    assert ed.scroll_to_block(head.id)
    bt.refresh()
    assert not bt.h_toc.isHidden()
    bt.h_toc.setChecked(False)
    assert next(b for b in ch.blocks if isinstance(b, HeadingBlock)).in_toc is False
    pb = next(b for b in ch.blocks if isinstance(b, PageBreakBlock))
    assert ed.scroll_to_block(pb.id)
    bt.refresh()
    bt.pb_recto.setChecked(True)
    assert next(b for b in ch.blocks if isinstance(b, PageBreakBlock)).recto is True


def test_relink_missing_images_workflow(window, tmp_path, monkeypatch):
    import zipfile
    from app.persistence.project_archive import load_project
    state = window.state
    asset = state.project.add_asset(make_png(200, 100), "logo.png")
    chapter(window).blocks.append(ImageBlock(asset=asset.id, alt="logo"))
    path = tmp_path / "with_image.bookforge"
    state.save(path)
    stripped = tmp_path / "lost.bookforge"
    with zipfile.ZipFile(path) as z, zipfile.ZipFile(stripped, "w") as out:
        for n in z.namelist():
            if not n.startswith("assets/"):
                out.writestr(n, z.read(n))
    state.open_project(stripped)
    assert not next(iter(state.project.assets.values())).data
    from app.services.validation_service import validate_book
    assert any(i.code == "missing_asset" for i in validate_book(state.project).errors)
    replacement = tmp_path / "found.png"
    replacement.write_bytes(make_png(300, 150, (1, 2, 3)))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(replacement), "")))
    assert window.relink_missing() == 1
    assert next(iter(state.project.assets.values())).width == 300
    assert not any(i.code == "missing_asset" for i in validate_book(state.project).errors)
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
    assert window.relink_missing() == 0
