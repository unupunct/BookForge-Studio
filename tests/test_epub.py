import io
import zipfile

import pytest
from lxml import etree
from PIL import Image

from app.domain.book import BookProject
from app.domain.content_blocks import (CodeBlock, HeadingBlock, ImageBlock, ListBlock, ParagraphBlock,
                                       PoetryBlock, QuoteBlock, RecipeBlock, Run, SceneBreakBlock, TableBlock)
from app.domain.sections import Section
from app.services.cover_presets import apply_preset
from app.services.epub_check import check_epub
from app.services.export_service import ExportError, export_other
from tests.conftest import LOREM, RO, make_png

NS = {"h": "http://www.w3.org/1999/xhtml", "o": "http://www.idpf.org/2007/opf"}


def epub_book():
    b = BookProject()
    b.metadata.title, b.metadata.author, b.metadata.language = "Cartea & \"Versuri\"", "Ion Țăranu", "ro"
    b.metadata.subtitle, b.metadata.year, b.metadata.rights = "Poeme", "2026", "Toate drepturile rezervate"
    pic = b.add_asset(make_png(800, 500, (20, 80, 160)), "pic.png")
    wp = io.BytesIO()
    Image.new("RGB", (60, 40), (200, 10, 10)).save(wp, "WEBP")
    web = b.add_asset(wp.getvalue(), "w.webp")
    b.sections = [
        Section("Cover", "front_cover", in_toc=False), Section("Title", "title_page", show_title=False),
        Section("Copyright", "copyright", show_title=False), Section("Contents", "toc", in_toc=False),
        Section("Capitolul 1", "chapter", blocks=[
            ParagraphBlock(runs=[Run(LOREM), Run("bold", bold=True), Run(" " + RO)]),
            HeadingBlock(level=1, runs=[Run("Secțiune")]),
            ParagraphBlock(runs=[Run("centrat")], align="center"),
            ListBlock(ordered=True, items=[[Run("unu")], [Run("doi")]]), QuoteBlock(runs=[Run("citat")]),
            CodeBlock(text="a < b && c > d"), SceneBreakBlock(),
            ImageBlock(asset=pic.id, caption=[Run("Figura <1>")], alt="albastru"),
            ImageBlock(asset=web.id, crop=[0.0, 0.0, 0.5, 1.0]),
            TableBlock(rows=[["A", "B"], ["1", "2"]], caption=[Run("Tab")])],
            children=[Section("Subcapitol", "section", blocks=[ParagraphBlock(runs=[Run("copil")])])]),
        Section("Poeme", "chapter", blocks=[
            PoetryBlock(title="Seară", text="Cade lumina\n  indentat\n\nA doua strofă\nultimul vers", signature="— A."),
            PoetryBlock(title="2", text="Un singur vers", align="center"),
            RecipeBlock(title="Supă", ingredients=["apă"], instructions=["fierbe"])]),
        Section("Back", "back_cover", in_toc=False)]
    apply_preset(b, "classic")
    return b


def read(z, name):
    return z.read(name).decode("utf-8")


def test_epub_is_structurally_valid_and_complete(tmp_path):
    b = epub_book()
    dest = tmp_path / "b.epub"
    res = export_other(b, dest, "epub")
    assert check_epub(dest) == []
    assert any("EpubCheck" in n for n in res.notes)
    with zipfile.ZipFile(dest) as z:
        names = z.namelist()
        assert names[0] == "mimetype" and z.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        opf = etree.fromstring(z.read("OEBPS/content.opf"))
        assert opf.get("version") == "3.0"
        assert opf.find(".//{http://purl.org/dc/elements/1.1/}language").text == "ro"
        assert opf.find(".//{http://purl.org/dc/elements/1.1/}creator").text == "Ion Țăranu"
        assert opf.find(".//{http://purl.org/dc/elements/1.1/}title").text == 'Cartea & "Versuri"'
        items = {i.get("id"): i for i in opf.findall(".//o:item", NS)}
        assert items["cover-img"].get("properties") == "cover-image"
        cover = Image.open(io.BytesIO(z.read("OEBPS/images/cover.png")))
        assert cover.height == 1600 and cover.width < cover.height
        text = "".join(read(z, n) for n in names if n.startswith("OEBPS/text/section-"))
        assert "Cade lumina<br/>" in text and "margin-left:1.0em" in text  # verse lines and indent kept
        assert "<strong>bold</strong>" in text and "text-align:center" in text
        assert "a &lt; b &amp;&amp; c &gt; d" in text and "Figura &lt;1&gt;" in text
        assert 'class="signature">— A.' in text and "poem center" in text
        assert "<ol><li>unu</li>" in text and "<h4>Ingrediente</h4>" in text  # book language is ro
        imgs = [n for n in names if n.startswith("OEBPS/images/img")]
        assert len(imgs) == 2 and all(n.endswith((".png", ".jpg")) for n in imgs)  # WebP converted
        nav = read(z, "OEBPS/nav.xhtml")
        assert "Capitolul 1" in nav and "Subcapitol" in nav and "Secțiune" in nav and "Poeme" in nav
        assert "Contents</a>" not in nav  # the generated contents page is not an entry
        assert "© 2026 Ion Țăranu" in read(z, "OEBPS/text/copyright.xhtml")
        assert "Toate drepturile rezervate" in read(z, "OEBPS/text/copyright.xhtml")


def test_poem_index_in_navigation(tmp_path):
    b = epub_book()
    b.settings.poem_index = "titles"
    dest = tmp_path / "p.epub"
    export_other(b, dest, "epub")
    assert check_epub(dest) == []
    with zipfile.ZipFile(dest) as z:
        nav = read(z, "OEBPS/nav.xhtml")
        assert "Index de poezii" in nav and "Seară" in nav and "2. Un singur vers" in nav


def test_large_section_is_split_into_files_and_links_resolve(tmp_path):
    b = BookProject()
    b.metadata.title = "Mare"
    b.sections = [Section("Poeme", "chapter", blocks=[
        PoetryBlock(title=str(i), text=f"vers {i}\nal doilea") for i in range(1, 601)])]
    b.settings.poem_index = "titles"
    dest = tmp_path / "m.epub"
    export_other(b, dest, "epub")
    assert check_epub(dest) == []
    with zipfile.ZipFile(dest) as z:
        parts = [n for n in z.namelist() if n.startswith("OEBPS/text/section-1-")]
        assert len(parts) >= 3
        assert "vers 600" in "".join(read(z, n) for n in parts)


def test_empty_book_and_no_cover_still_valid(tmp_path):
    b = BookProject()
    b.metadata.title = "Gol"
    b.sections = []
    dest = tmp_path / "e.epub"
    res = export_other(b, dest, "epub")
    assert check_epub(dest) == [] and any("no content" in n for n in res.notes)
    b2 = BookProject()
    b2.metadata.title = "Fără copertă"
    b2.sections = [Section("C", "chapter", blocks=[ParagraphBlock(runs=[Run("x")])])]
    d2 = tmp_path / "n.epub"
    export_other(b2, d2, "epub")
    assert check_epub(d2) == []
    with zipfile.ZipFile(d2) as z:
        assert "OEBPS/images/cover.png" not in z.namelist()


def test_checker_detects_broken_packages(tmp_path):
    good = tmp_path / "g.epub"
    export_other(epub_book(), good, "epub")
    with zipfile.ZipFile(good) as z:
        files = {n: z.read(n) for n in z.namelist()}

    def rewrite(name, mutate, stored_mimetype=True, drop=None):
        out = tmp_path / name
        with zipfile.ZipFile(out, "w") as z:
            order = list(files)
            if not stored_mimetype:
                order = order[1:] + order[:1]
            for n in order:
                if n == drop:
                    continue
                data = mutate(n, files[n])
                comp = zipfile.ZIP_STORED if n == "mimetype" and stored_mimetype else zipfile.ZIP_DEFLATED
                z.writestr(zipfile.ZipInfo(n), data, compress_type=comp)
        return out
    assert any("first entry" in p for p in check_epub(rewrite("a.epub", lambda n, d: d, stored_mimetype=False)))
    assert any("missing from the archive" in p for p in check_epub(rewrite("b.epub", lambda n, d: d, drop="OEBPS/style.css")))
    bad_xml = rewrite("c.epub", lambda n, d: d + b"<oops" if n == "OEBPS/text/titlepage.xhtml" else d)
    assert any("not well-formed" in p for p in check_epub(bad_xml))
    broken_link = rewrite("d.epub", lambda n, d: d.replace(b'src="../images/cover.png"', b'src="../images/nope.png"')
                          if n == "OEBPS/text/cover.xhtml" else d)
    assert any("missing file" in p for p in check_epub(broken_link))
    bad_frag = rewrite("e.epub", lambda n, d: d.replace(b"#sec-", b"#zzz-") if n == "OEBPS/nav.xhtml" else d)
    assert any("missing id" in p for p in check_epub(bad_frag))
    not_zip = tmp_path / "f.epub"
    not_zip.write_bytes(b"nope")
    assert check_epub(not_zip)


def test_epub_export_protects_existing_file_and_leaves_no_temp(tmp_path):
    b = epub_book()
    dest = tmp_path / "x.epub"
    dest.write_bytes(b"precious")
    with pytest.raises(ExportError, match="already exists"):
        export_other(b, dest, "epub")
    assert dest.read_bytes() == b"precious"
    export_other(b, dest, "epub", overwrite=True)
    assert check_epub(dest) == [] and not list(tmp_path.glob(".*.tmp"))
