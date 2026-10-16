import sys, os, tempfile, copy
ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["BOOKFORGE_DATA_DIR"] = tempfile.mkdtemp()
from pathlib import Path
import pymupdf
from PIL import Image, ImageDraw, ImageFont
from app.domain.content_blocks import ParagraphBlock, HeadingBlock, RecipeBlock, Run
from app.domain.sections import Section
from app.importers.base import ImportOptions
from app.services.export_service import export_pdf
from app.services.import_service import run_import
from app.services.project_service import NewBookSpec, create_project
from app.services.template_service import TemplateService

root = ROOT / "samples"
out = root / "output" / "templates"
out.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())

staged = run_import(root / "unupunctpoezie_colectie_facebook.docx", ImportOptions())
poems = [b for s in staged.result.sections for b in s.walk_blocks()] if hasattr(Section, "walk_blocks") else \
    [b for s in staged.result.sections for t in s.walk() for b in t.blocks]
poems = [b for b in poems if b.type == "poetry" and 4 <= len(b.text.strip().splitlines()) <= 22][:8]
assert len(poems) >= 4, len(poems)

PROSE = [
    "Dimineața venea încet peste oraș, iar luminile străzii se stingeau una câte una, ca niște gânduri pe care nu "
    "mai avea cine să le gândească. Maria deschise fereastra și lăsă aerul rece să intre în casă.",
    "— Ai auzit și tu? întrebă ea. Cineva urca scările, deși de ani de zile nu mai locuia nimeni la etajul de sus. "
    "Pașii se opriră dinaintea ușii, apoi se auzi, foarte clar, o bătaie scurtă.",
    "Își aminti de scrisoarea din sertar, de vorbele bunicului și de drumul lung prin pădure. Nimic nu fusese "
    "întâmplător; fiecare lucru își avea locul și timpul lui, iar acum timpul venise să se arate.",
    "Peste câteva clipe, casa era din nou liniștită. Doar ceasul din hol bătea rar, cu o răbdare veche, și în aerul "
    "dimineții plutea un miros de ceai și de hârtie îngălbenită.",
]

try:
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26)
    small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)
except OSError:
    font = small = ImageFont.load_default()

svc = TemplateService()
sheets, covers = [], []
for t in svc.list_templates():
    key, name = t["key"], t["name"]
    poetry = "poetry" in key
    spec = NewBookSpec(title="Poezii alese" if poetry else "Lumina din Nord", author="Unupunct" if poetry else "Ana Popescu",
                       language="ro", profile="poetry" if poetry else ("cookbook" if key == "cookbook" else "novel"),
                       template=key, toc=False)
    b = create_project(spec, svc)
    for s in b.sections:
        if s.kind == "copyright":
            s.enabled = False
    ch = next(s for s in b.sections if s.kind == "chapter")
    if poetry:
        ch.title = "Poezii"
        ch.blocks = [copy.deepcopy(p) for p in poems]
        marker = poems[0].title or poems[0].text.split()[0]
    elif key == "cookbook":
        ch.title = "Supe"
        ch.blocks = [RecipeBlock(title="Ciorbă de legume", prep_time="15 min", cook_time="40 min", servings="4",
                                 ingredients=["2 morcovi", "1 țelină", "1 ceapă", "sare, piper"],
                                 instructions=["Taie legumele cubulețe.", "Fierbe 40 de minute."], notes="Se servește caldă.")]
        marker = "Ciorbă"
    else:
        ch.title = "Capitolul întâi"
        ch.blocks = [ParagraphBlock(runs=[Run(p)]) for p in PROSE * 3]
        marker = "Dimineața venea"
    pdf = tmp / f"{key}.pdf"
    export_pdf(b, pdf, "digital", overwrite=True, allow_errors=True)
    doc = pymupdf.open(str(pdf))
    first = next((i for i in range(1, doc.page_count) if marker in doc[i].get_text()), min(2, doc.page_count - 1))
    idx = [0, first] + ([first + 1] if first + 1 < doc.page_count else [])
    imgs = []
    for i in idx:
        pix = doc[i].get_pixmap(dpi=110)
        imgs.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    H = 640
    imgs = [im.resize((int(im.width * H / im.height), H), Image.LANCZOS) for im in imgs]
    W = sum(im.width for im in imgs) + 30 * (len(imgs) + 1)
    sheet = Image.new("RGB", (max(W, 900), H + 120), "white")
    d = ImageDraw.Draw(sheet)
    d.text((30, 18), name, fill="#222", font=font)
    st = b.settings
    d.text((30, 58), f"{key}  |  {st.width_mm:.0f}x{st.height_mm:.0f} mm  |  {st.body_font} {st.body_size:g} pt  |  "
                     f"chapter numbering: {st.chapter_number_style}, ornament: {st.chapter_ornament}", fill="#666", font=small)
    x = 30
    for im in imgs:
        sheet.paste(im, (x, 100))
        d.rectangle([x - 1, 99, x + im.width, 100 + im.height], outline="#bbb")
        x += im.width + 30
    sheet.save(out / f"{key}.png")
    sheets.append(sheet.convert("RGB"))
    covers.append((name, imgs[0]))
    print("ok", key, doc.page_count, idx)

# gallery PDF: one template per page
sheets[0].save(out / "template_gallery.pdf", save_all=True, append_images=sheets[1:], resolution=110)

# overview mosaic of covers
cols, th = 6, 300
cells = [(n, im.resize((int(im.width * th / im.height), th), Image.LANCZOS)) for n, im in covers]
cw = max(c.width for _, c in cells) + 24
rows = (len(cells) + cols - 1) // cols
mos = Image.new("RGB", (cols * cw + 24, rows * (th + 56) + 24), "white")
md = ImageDraw.Draw(mos)
for i, (n, c) in enumerate(cells):
    x, y = 24 + (i % cols) * cw, 24 + (i // cols) * (th + 56)
    mos.paste(c, (x, y))
    md.text((x, y + th + 6), n[:26], fill="#222", font=small)
mos.save(out / "overview_covers.png")
print("done", len(sheets))
