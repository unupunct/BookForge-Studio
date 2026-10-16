"""Renders the pictures used in README.md from neutral, synthetic content (no personal manuscripts).

Run on Windows with a real display platform so text renders properly:
    set QT_QPA_PLATFORM=windows & .venv\\Scripts\\python scripts\\make_readme_images.py
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOOKFORGE_DATA_DIR", tempfile.mkdtemp())

import pymupdf  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.domain.book import BookProject  # noqa: E402
from app.domain.content_blocks import (HeadingBlock, ImageBlock, LayoutBlock, ParagraphBlock, PoetryBlock,  # noqa: E402
                                       Run, TextBoxBlock)
from app.domain.sections import Section  # noqa: E402
from app.services.export_service import export_pdf  # noqa: E402
from app.services.project_service import NewBookSpec, create_project  # noqa: E402
from app.services.template_service import TemplateService  # noqa: E402

OUT = ROOT / "docs" / "images"
OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp())
svc = TemplateService()

PROSE = ("Dimineața venea încet peste oraș, iar luminile străzii se stingeau una câte una, ca niște gânduri pe care "
         "nu mai avea cine să le gândească. Maria deschise fereastra și lăsă aerul rece să intre în casă. ")
POEM = ["Astăzi încerc să nu mă scufund", "în lucrurile care încă nu s-au întâmplat.", "Îmi pun ziua sub tălpi",
        "ca pe o scândură subțire", "și merg.", "", "Iar eu, undeva între ele,", "țin brațele desfăcute",
        "ca și cum aș putea îmbrățișa", "un echilibru."]


def photo(w: int, h: int, c1: str, c2: str) -> bytes:
    im = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(im)
    for i in range(0, w, 48):
        d.line([(i, 0), (w - i, h)], fill=c2, width=6)
    d.ellipse([w * 0.62, h * 0.12, w * 0.86, h * 0.12 + w * 0.24], fill="#fff3c4")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def font(size: int):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)
    except OSError:
        return ImageFont.load_default()


def page_image(doc, i: int, dpi: int = 100) -> Image.Image:
    pix = doc[i].get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


# ----------------------------------------------------------------------------- 1. template covers
def templates_overview() -> None:
    covers = []
    for t in svc.list_templates():
        poetry = "poetry" in t["key"]
        b = create_project(NewBookSpec(title="Poezii alese" if poetry else "Lumina din Nord",
                                       author="Autor Exemplu", language="ro",
                                       profile="poetry" if poetry else "novel", template=t["key"], toc=False), svc)
        b.sections = [s for s in b.sections if s.kind == "front_cover"]
        pdf = TMP / f"{t['key']}.pdf"
        export_pdf(b, pdf, "digital", overwrite=True, allow_errors=True)
        covers.append((t["name"], page_image(pymupdf.open(str(pdf)), 0, 60)))
    th, cols = 250, 7
    cells = [(n, im.resize((int(im.width * th / im.height), th), Image.LANCZOS)) for n, im in covers]
    cw = max(c.width for _, c in cells) + 22
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw + 22, rows * (th + 44) + 22), "#f6f4ef")
    d = ImageDraw.Draw(sheet)
    for i, (n, c) in enumerate(cells):
        x, y = 22 + (i % cols) * cw, 22 + (i // cols) * (th + 44)
        sheet.paste(c, (x, y))
        d.text((x, y + th + 6), n[:24], fill="#333", font=font(14))
    sheet.save(OUT / "templates.png")
    print("templates.png", sheet.size)


# ----------------------------------------------------------------------------- 2. page layouts
def layouts_book() -> BookProject:
    b = create_project(NewBookSpec(title="Lumina din Nord", author="Autor Exemplu", language="ro",
                                   profile="novel", template="modern_novel", toc=False), svc)
    a1 = b.add_asset(photo(1200, 800, "#2a6f97", "#ffd166"), "marea.jpg").id
    a2 = b.add_asset(photo(800, 1100, "#52796f", "#f2e8cf"), "padure.jpg").id
    paras = lambda n: [ParagraphBlock(runs=[Run(PROSE * 3)]) for _ in range(n)]
    cols = Section("Două coloane", "chapter", blocks=paras(8))
    cols.page = {"columns": 2, "column_gap_mm": 7}
    wrap = Section("Imagine cu text", "chapter", blocks=[
        ImageBlock(asset=a1, width_pct=45, place="wrap_left", caption=[Run("Marea, într-o dimineață de iarnă")])]
        + paras(3) + [ImageBlock(asset=a2, width_pct=34, place="wrap_right")] + paras(2))
    pinned = Section("Plasare liberă", "chapter", blocks=paras(1) + [
        ImageBlock(asset=a1, place="page", px=0.5, py=0.5, pw=0.36, rotation=7),
        TextBoxBlock(text="Notă fixată\npe pagină", px=0.12, py=0.58, pw=0.3, ph=0.12, size=14, bold=True,
                     background="#FFE9A8", align="center", valign="middle")])
    special = Section("Pagini speciale", "chapter", blocks=[
        LayoutBlock(layout="photo_full", asset=a1, headline="Marea de iarnă", text="Fotografie pe toată pagina."),
        LayoutBlock(layout="image_left", asset=a2, headline="Fig. 1", text=PROSE * 4, image_pct=42),
        LayoutBlock(layout="quote_page", text="Nu tot timpul e doar timp.", headline="— Autor Exemplu")])
    keep = [s for s in b.sections if s.kind in ("front_cover", "title_page")]
    b.sections = keep + [cols, wrap, pinned, special]
    return b


def layouts_sheet() -> None:
    b = layouts_book()
    pdf = TMP / "layouts.pdf"
    export_pdf(b, pdf, "digital", overwrite=True, allow_errors=True)
    doc = pymupdf.open(str(pdf))
    want = []
    for i in range(doc.page_count):
        txt = doc[i].get_text()
        if i == 0 or "Două coloane" in txt or "Imagine cu text" in txt or "Plasare liberă" in txt:
            want.append(i)
    want += [i for i in range(doc.page_count) if doc[i].get_images() and i not in want][:3]
    want = sorted(set(want))[:6]
    ims = [page_image(doc, i, 70) for i in want]
    h = 330
    ims = [im.resize((int(im.width * h / im.height), h), Image.LANCZOS) for im in ims]
    sheet = Image.new("RGB", (sum(im.width for im in ims) + 14 * (len(ims) + 1), h + 28), "#d9d6ce")
    x = 14
    for im in ims:
        sheet.paste(im, (x, 14))
        x += im.width + 14
    sheet.save(OUT / "layouts.png")
    print("layouts.png", sheet.size, want)


# ----------------------------------------------------------------------------- 3. screen PDF
def screen_sheet() -> None:
    b = layouts_book()
    shots = []
    for dark, size in ((False, "phone"), (True, "phone"), (False, "tablet")):
        pdf = TMP / f"s-{size}-{dark}.pdf"
        export_pdf(b, pdf, "screen", overwrite=True, allow_errors=True, screen_size=size, screen_dark=dark)
        doc = pymupdf.open(str(pdf))
        idx = next(i for i in range(doc.page_count) if "Imagine cu text" in doc[i].get_text()) + 1
        shots.append(page_image(doc, idx, 90))
    h = 420
    shots = [im.resize((int(im.width * h / im.height), h), Image.LANCZOS) for im in shots]
    sheet = Image.new("RGB", (sum(im.width for im in shots) + 20 * (len(shots) + 1), h + 40), "#eceae4")
    x = 20
    for im in shots:
        sheet.paste(im, (x, 20))
        x += im.width + 20
    sheet.save(OUT / "screen-pdf.png")
    print("screen-pdf.png", sheet.size)


# ----------------------------------------------------------------------------- 4. the application window
def app_screens() -> None:
    from PySide6.QtCore import QCoreApplication, QEventLoop
    from PySide6.QtWidgets import QApplication
    from app.application_state import AppState
    from app.main_window import MainWindow
    from app.services.autosave_service import AutosaveService
    from app.services.project_service import SettingsStore
    from app.ui import theme
    import time

    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    tmp = Path(tempfile.mkdtemp())
    state = AppState(autosave=AutosaveService(tmp / "rec"), settings=SettingsStore(tmp / "s.json"))
    (tmp / "rec").mkdir(exist_ok=True)
    state.settings_store.data.autosave_seconds = 0
    state.apply_autosave_interval()
    win = MainWindow(state)
    win.resize(1500, 920)
    win.show()
    b = layouts_book()
    state.install_project(b)

    def pump(cond, timeout=20.0):
        end = time.time() + timeout
        while time.time() < end:
            QCoreApplication.processEvents(QEventLoop.AllEvents, 30)
            if cond():
                return True
            time.sleep(0.02)
        return cond()

    pump(lambda: state.layout is not None)
    pinned = next(s for s in b.sections if s.title == "Plasare liberă")
    win.navigator.rebuild()
    win.navigator.select(pinned.id)
    pump(lambda: False, 1.5)
    win.grab().save(str(OUT / "app-editor.png"))
    # preview with a pinned image selected
    win.tabs.setCurrentWidget(win.preview)
    img = next(x for x in pinned.blocks if getattr(x, "place", "") == "page")
    page = next(p for p in state.layout.pages if img.id in {getattr(i, "block_id", None) for i in p.items})
    win.preview.set_layout(state.layout)
    win.preview.show_page(page.index)
    win.preview.zoom.setCurrentText("Fit page")
    pump(lambda: False, 0.8)
    win.preview.canvas.selected = img.id
    win.preview.canvas.update()
    pump(lambda: False, 0.5)
    win.grab().save(str(OUT / "app-preview.png"))
    print("app screenshots done")
    state.layout_controller.wait_idle()
    state._autosave_timer.stop()
    win.close()


if __name__ == "__main__":
    which = sys.argv[1:] or ["templates", "layouts", "screen", "app"]
    if "templates" in which:
        templates_overview()
    if "layouts" in which:
        layouts_sheet()
    if "screen" in which:
        screen_sheet()
    if "app" in which:
        app_screens()
