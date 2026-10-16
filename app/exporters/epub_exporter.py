"""EPUB 3 export (reflowable) with an EPUB 2 NCX for older readers.

Content is written as XHTML from the structured blocks (not from the print layout): chapters,
headings, lists, quotes, poems with every line break and stanza, images with captions, tables.
The result is checked structurally by services/epub_check.py after writing. It is NOT validated
with the W3C EpubCheck tool; run that before submitting to a store.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ..domain.book import BookProject
from ..domain.content_blocks import (Block, CodeBlock, ExerciseBlock, FootnoteBlock, HeadingBlock,
                                     ImageBlock, ListBlock, PageBreakBlock, ParagraphBlock,
                                     PoetryBlock, QuoteBlock, RecipeBlock, Run, SceneBreakBlock,
                                     TableBlock, runs_text)
from ..domain.sections import GENERATED_KINDS, Section
from ..i18n import exercise_label, tr
from ..layout.page_builder import poem_entries
from ..services.image_service import prepare_image

XHTML_NS = "http://www.w3.org/1999/xhtml"
EPUB_NS = "http://www.idpf.org/2007/ops"
MAX_BLOCKS_PER_FILE = 250
_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")

CSS = """
html { font-family: serif; }
body { margin: 5%; line-height: 1.5; }
h1, h2, h3, h4, h5, h6 { font-family: sans-serif; line-height: 1.25; page-break-after: avoid; }
h1 { text-align: center; margin: 2em 0 1em; }
p { margin: 0; text-align: justify; }
p + p { text-indent: 1.2em; }
p.noindent, h1 + p, h2 + p, h3 + p { text-indent: 0; }
blockquote { margin: 1em 2em; font-style: italic; }
blockquote footer { text-align: right; font-style: normal; }
pre { white-space: pre-wrap; font-family: monospace; font-size: 0.85em; background: #f3f3f3; padding: .6em; }
figure { margin: 1em 0; text-align: center; page-break-inside: avoid; }
figure img { max-width: 100%; height: auto; }
figcaption { font-size: .85em; font-style: italic; }
table { border-collapse: collapse; margin: 1em 0; }
td, th { border: 1px solid #888; padding: .25em .5em; }
.poem { margin: 1.4em 0; page-break-inside: auto; }
.poem p { text-align: left; text-indent: 0; margin: 0 0 1em 0; }
.poem.center p { text-align: center; }
.poem-title { font-size: 1.1em; margin: 1.6em 0 .6em; text-align: left; }
.signature { text-align: right; font-style: italic; font-size: .9em; text-indent: 0; }
.scene { text-align: center; margin: 1em 0; text-indent: 0; }
.callout { background: #f6f1e7; border-left: 4px solid #c97b3c; padding: .4em .8em; margin: 1em 0; }
.titlepage { text-align: center; margin-top: 25%; }
.titlepage p { text-align: center; text-indent: 0; }
.cover img { max-width: 100%; max-height: 100%; }
nav ol { list-style: none; padding-left: 1em; }
"""


def _x(text: str) -> str:
    return escape(_BAD.sub("", text))


def _attr(text: str) -> str:
    return quoteattr(_BAD.sub("", text))


@dataclass
class _Item:
    id: str
    href: str
    media: str
    props: str = ""
    data: bytes = b""


@dataclass
class _Nav:
    title: str
    href: str
    children: list["_Nav"] = field(default_factory=list)


class _Builder:
    def __init__(self, book: BookProject):
        self.book = book
        self.md = book.metadata
        self.images: dict[str, _Item] = {}
        self.pages: list[_Item] = []
        self.nav: list[_Nav] = []
        self.notes: list[str] = []
        self.poem_files: dict[str, str] = {}  # block id -> href

    # ---------------------------------------------------------------- inline
    def runs(self, runs: list[Run]) -> str:
        out = []
        for r in runs:
            t = _x(r.text).replace("\n", "<br/>").replace(chr(31), " ")
            if r.code:
                t = f"<code>{t}</code>"
            if r.bold:
                t = f"<strong>{t}</strong>"
            if r.italic:
                t = f"<em>{t}</em>"
            if r.underline:
                t = f'<span style="text-decoration:underline">{t}</span>'
            if r.strike:
                t = f"<s>{t}</s>"
            if r.sup:
                t = f"<sup>{t}</sup>"
            elif r.sub:
                t = f"<sub>{t}</sub>"
            if r.link and r.link.lower().startswith(("http://", "https://", "mailto:")):
                t = f"<a href={_attr(r.link)}>{t}</a>"
            out.append(t)
        return "".join(out)

    # ---------------------------------------------------------------- images
    def image(self, asset_id: str, crop=None) -> _Item | None:
        asset = self.book.assets.get(asset_id)
        if asset is None or not asset.data:
            self.notes.append("A missing image was left out of the EPUB")
            return None
        key = f"{asset_id}:{crop}"
        if key in self.images:
            return self.images[key]
        data, fmt = prepare_image(asset, tuple(crop) if crop else None, 1600 / 200 * 72, 200, 85)
        ext, media = ("png", "image/png") if fmt == "PNG" else ("jpg", "image/jpeg")
        item = _Item(f"img{len(self.images) + 1}", f"images/img{len(self.images) + 1}.{ext}", media, data=data)
        self.images[key] = item
        return item

    # ---------------------------------------------------------------- blocks
    def block(self, b: Block, depth: int) -> str:
        if isinstance(b, ParagraphBlock):
            style = []
            if b.align in ("center", "right", "left", "justify"):
                style.append(f"text-align:{b.align}")
            if b.left_indent:
                style.append(f"margin-left:{b.left_indent / 12:.2f}em")
            if b.first_indent is not None:
                style.append(f"text-indent:{b.first_indent / 12:.2f}em")
            if b.space_before:
                style.append(f"margin-top:{b.space_before / 12:.2f}em")
            if b.space_after:
                style.append(f"margin-bottom:{b.space_after / 12:.2f}em")
            st = f' style="{";".join(style)}"' if style else ""
            return f"<p{st}>{self.runs(b.runs)}</p>"
        if isinstance(b, HeadingBlock):
            lvl = min(depth + b.level, 6)
            return f'<h{lvl} id="blk-{b.id}">{self.runs(b.runs)}</h{lvl}>'
        if isinstance(b, ListBlock):
            tag = "ol" if b.ordered else "ul"
            return f"<{tag}>" + "".join(f"<li>{self.runs(i)}</li>" for i in b.items) + f"</{tag}>"
        if isinstance(b, QuoteBlock):
            attr = f"<footer>— {self.runs(b.attribution)}</footer>" if b.attribution else ""
            return f"<blockquote><p>{self.runs(b.runs)}</p>{attr}</blockquote>"
        if isinstance(b, CodeBlock):
            return f"<pre><code>{_x(b.text)}</code></pre>"
        if isinstance(b, PoetryBlock):
            return self.poem(b, depth)
        if isinstance(b, ImageBlock):
            it = self.image(b.asset, b.crop)
            if it is None:
                return ""
            cap = f"<figcaption>{self.runs(b.caption)}</figcaption>" if b.caption else ""
            return (f'<figure><img src={_attr("../" + it.href)} alt={_attr(b.alt or runs_text(b.caption) or "image")} '
                    f'style="width:{min(max(b.width_pct, 10), 100):.0f}%"/>{cap}</figure>')
        if isinstance(b, TableBlock):
            rows = []
            for i, r in enumerate(b.rows):
                tag = "th" if i < b.header_rows else "td"
                rows.append("<tr>" + "".join(f"<{tag}>{_x(c)}</{tag}>" for c in r) + "</tr>")
            cap = f"<caption>{self.runs(b.caption)}</caption>" if b.caption else ""
            return f"<table>{cap}{''.join(rows)}</table>"
        if isinstance(b, SceneBreakBlock):
            return f'<p class="scene">{_x(b.glyph)}</p>'
        if isinstance(b, PageBreakBlock):
            return ""  # reflowable: reading systems paginate themselves
        if isinstance(b, RecipeBlock):
            lvl = min(depth + 1, 6)
            parts = [f'<h{lvl} id="blk-{b.id}">{_x(b.title)}</h{lvl}>']
            lg = self.md.language
            meta = [f"{k}: {_x(v)}" for k, v in ((tr("prep", lg), b.prep_time), (tr("cook", lg), b.cook_time),
                                                  (tr("serves", lg), b.servings)) if v]
            if meta:
                parts.append(f'<p class="noindent"><em>{" · ".join(meta)}</em></p>')
            if b.image:
                it = self.image(b.image)
                if it:
                    parts.append(f'<figure><img src={_attr("../" + it.href)} alt={_attr(b.title or "recipe")}/></figure>')
            if b.description:
                parts.append(f"<p>{_x(b.description)}</p>")
            if b.ingredients:
                parts.append(f"<h4>{_x(tr('ingredients', lg))}</h4><ul>" + "".join(f"<li>{_x(i)}</li>" for i in b.ingredients) + "</ul>")
            if b.instructions:
                parts.append(f"<h4>{_x(tr('method', lg))}</h4><ol>" + "".join(f"<li>{_x(i)}</li>" for i in b.instructions) + "</ol>")
            if b.notes:
                parts.append(f"<p><strong>Notes:</strong> {_x(b.notes)}</p>")
            if b.nutrition:
                parts.append(f"<p><strong>Nutrition (as supplied):</strong> {_x(b.nutrition)}</p>")
            return "".join(parts)
        if isinstance(b, ExerciseBlock):
            label = exercise_label(b.kind, self.md.language)
            head = f"{label}: {b.title}" if b.title else label
            return f'<div class="callout"><p><strong>{_x(head)}</strong> {self.runs(b.runs)}</p></div>'
        if isinstance(b, FootnoteBlock):
            return f'<p class="noindent"><small><strong>{_x(b.label)}</strong> {self.runs(b.runs)}</small></p>'
        return ""

    def poem(self, b: PoetryBlock, depth: int) -> str:
        lvl = min(depth + 2, 6)
        out = []
        if b.title:
            out.append(f'<h{lvl} class="poem-title" id="blk-{b.id}">{_x(b.title)}</h{lvl}>')
        cls = "poem center" if b.align == "center" else "poem"
        ident = "" if b.title else f' id="blk-{b.id}"'
        stanzas, cur = [], []
        for line in b.text.replace("\r", "").split("\n"):
            if line.strip():
                cur.append(line.expandtabs(4))
            elif cur:
                stanzas.append(cur)
                cur = []
        if cur:
            stanzas.append(cur)
        body = []
        for st in stanzas:
            lines = []
            for ln in st:
                lead = len(ln) - len(ln.lstrip(" "))
                txt = _x(ln.strip())
                lines.append(f'<span style="margin-left:{lead * 0.5:.1f}em">{txt}</span>' if lead else txt)
            body.append("<p>" + "<br/>".join(lines) + "</p>")
        out.append(f'<div class="{cls}"{ident}>{"".join(body)}</div>')
        if b.signature.strip():
            out.append(f'<p class="signature">{_x(b.signature.strip())}</p>')
        return "".join(out)

    # -------------------------------------------------------------- sections
    def xhtml(self, title: str, body: str, cls: str = "") -> bytes:
        lang = _x(self.md.language or "en")
        c = f' class="{cls}"' if cls else ""
        return (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
                f'<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" lang="{lang}" xml:lang="{lang}">'
                f'<head><meta charset="utf-8"/><title>{_x(title)}</title>'
                f'<link rel="stylesheet" type="text/css" href="../style.css"/></head><body{c}>{body}</body></html>'
                ).encode("utf-8")

    def section_files(self, section: Section, index: int) -> tuple[list[_Item], _Nav]:
        """One section (with its sub-sections) -> one or more XHTML files and its nav subtree."""
        chunks: list[list[str]] = [[]]
        nav_children: list[_Nav] = []
        toc_depth = self.book.settings.toc_depth
        count = 0
        ids_in_chunk: list[list[tuple[str, str, int]]] = [[]]

        def add(html: str, nav_entry: tuple[str, str, int] | None = None) -> None:
            nonlocal count
            if count >= MAX_BLOCKS_PER_FILE:
                chunks.append([])
                ids_in_chunk.append([])
                count = 0
            chunks[-1].append(html)
            if nav_entry:
                ids_in_chunk[-1].append(nav_entry)
            count += 1

        def walk(s: Section, depth: int) -> None:
            if not s.enabled:
                return
            if s.title.strip() and s.show_title:
                lvl = min(depth, 6)
                add(f'<h{lvl} id="sec-{s.id}">{_x(s.title)}</h{lvl}>',
                    (s.title, f"sec-{s.id}", depth) if depth > 1 and s.in_toc else None)
            for b in s.blocks:
                html = self.block(b, depth)
                if not html:
                    continue
                entry = None
                if isinstance(b, HeadingBlock) and b.in_toc and depth + b.level <= toc_depth:
                    entry = (runs_text(b.runs), f"blk-{b.id}", depth + b.level)
                add(html, entry)
            for c in s.children:
                walk(c, depth + 1)

        walk(section, 1)
        items: list[_Item] = []
        top = _Nav(section.title or "Untitled", "")
        for n, (chunk, entries) in enumerate(zip(chunks, ids_in_chunk)):
            suffix = "" if len(chunks) == 1 else f"-{n + 1}"
            href = f"text/section-{index}{suffix}.xhtml"
            items.append(_Item(f"sec{index}{suffix}", href, "application/xhtml+xml",
                               data=self.xhtml(section.title or self.md.title, "".join(chunk))))
            if n == 0:
                top.href = f"section-{index}{suffix}.xhtml#sec-{section.id}" if (section.title.strip() and section.show_title) \
                    else f"section-{index}{suffix}.xhtml"
            for title, frag, depth in entries:
                top.children.append(_Nav(title, f"section-{index}{suffix}.xhtml#{frag}"))
        for n, chunk in enumerate(chunks):
            suffix = "" if len(chunks) == 1 else f"-{n + 1}"
            joined = "".join(chunk)
            for s in section.walk():
                for b in s.blocks:
                    if isinstance(b, PoetryBlock) and f'id="blk-{b.id}"' in joined:
                        self.poem_files[b.id] = f"section-{index}{suffix}.xhtml#blk-{b.id}"
        return items, top

    # ----------------------------------------------------------------- build
    def front_pages(self, cover_png: bytes | None) -> list[_Item]:
        pages: list[_Item] = []
        if cover_png:
            body = f'<div class="cover"><img src="../images/cover.png" alt="Cover"/></div>'
            pages.append(_Item("cover", "text/cover.xhtml", "application/xhtml+xml",
                               data=self.xhtml("Cover", body, "cover")))
        md = self.md
        tp = [f"<h1>{_x(md.title)}</h1>"]
        if md.subtitle:
            tp.append(f"<p><em>{_x(md.subtitle)}</em></p>")
        if md.author:
            tp.append(f"<p>{_x(md.author)}</p>")
        if md.publisher:
            tp.append(f"<p><small>{_x(md.publisher)}</small></p>")
        pages.append(_Item("titlepage", "text/titlepage.xhtml", "application/xhtml+xml",
                           data=self.xhtml(md.title, f'<div class="titlepage">{"".join(tp)}</div>')))
        legal = []
        if md.author.strip():
            legal.append(f"© {md.year} {md.author}".replace("  ", " ").strip())
        legal.extend(l for l in md.rights.splitlines() if l.strip())
        if md.isbn.strip():
            legal.append(f"ISBN {md.isbn}")
        if legal and any(s.kind == "copyright" and s.enabled for s in self.book.sections):
            pages.append(_Item("copyright", "text/copyright.xhtml", "application/xhtml+xml",
                               data=self.xhtml("Copyright", "".join(f'<p class="noindent"><small>{_x(l)}</small></p>'
                                                                    for l in legal))))
        return pages


def _cover_png(book: BookProject) -> bytes | None:
    """Render the front cover through the same cover pipeline as the print/PDF cover exports."""
    cv = book.settings.cover
    if not cv.enabled or not any(s.kind == "front_cover" and s.enabled for s in book.sections):
        return None
    import pymupdf
    from ..exporters.pdf_exporter import PROFILES, render_pdf
    from ..services.cover_service import build_cover_layout
    layout = build_cover_layout(book, "front")
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "cover.pdf"
        render_pdf(book, layout, pdf, PROFILES["digital"])
        with pymupdf.open(str(pdf)) as doc:
            page = doc[0]
            zoom = 1600.0 / page.rect.height
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


def export_epub(book: BookProject, path: Path) -> list[str]:
    bld = _Builder(book)
    md = book.metadata
    cover = _cover_png(book)
    front = bld.front_pages(cover)
    body_items: list[_Item] = []
    navs: list[_Nav] = []
    idx = 0
    for s in book.sections:
        if not s.enabled or s.kind in ("front_cover", "back_cover", "toc", "copyright"):
            continue
        if s.kind in GENERATED_KINDS and not s.blocks:
            continue
        idx += 1
        items, nav = bld.section_files(s, idx)
        body_items.extend(items)
        if s.in_toc and (s.title.strip() or nav.children):
            navs.append(nav)
    if not body_items:
        body_items.append(_Item("sec1", "text/section-1.xhtml", "application/xhtml+xml",
                                data=bld.xhtml(md.title, "<p>This book has no content yet.</p>")))
        navs.append(_Nav(md.title, "section-1.xhtml"))
        bld.notes.append("The book has no content")
    poem_nav: list[_Nav] = []
    for e in poem_entries(book):
        href = bld.poem_files.get(e.anchor[4:])
        if href:
            poem_nav.append(_Nav(e.title, href))
    if poem_nav:
        navs.append(_Nav(tr("poem_index", md.language), poem_nav[0].href, poem_nav))

    uid = "urn:uuid:" + str(uuid.UUID(int=int(hashlib.md5(book.id.encode()).hexdigest(), 16)))
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest: list[_Item] = [
        _Item("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        _Item("ncx", "toc.ncx", "application/x-dtbncx+xml"),
        _Item("css", "style.css", "text/css", data=CSS.strip().encode("utf-8")),
    ]
    if cover:
        manifest.append(_Item("cover-img", "images/cover.png", "image/png", "cover-image", cover))
    manifest.extend(front)
    manifest.extend(body_items)
    manifest.extend(bld.images.values())

    def nav_li(n: _Nav) -> str:
        href = f"text/{n.href}"
        kids = "<ol>" + "".join(nav_li(c) for c in n.children) + "</ol>" if n.children else ""
        return f"<li><a href={_attr(href)}>{_x(n.title)}</a>{kids}</li>"

    toc_items = "".join(nav_li(n) for n in navs)
    first_text = body_items[0].href
    landmarks = (f'<nav epub:type="landmarks" hidden="hidden"><ol>'
                 + ("<li><a epub:type=\"cover\" href=\"text/cover.xhtml\">Cover</a></li>" if cover else "")
                 + f'<li><a epub:type="bodymatter" href={_attr(first_text)}>Start</a></li></ol></nav>')
    nav_doc = (f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="{XHTML_NS}" xmlns:epub="{EPUB_NS}" '
               f'lang="{_x(md.language or "en")}" xml:lang="{_x(md.language or "en")}"><head><meta charset="utf-8"/>'
               f'<title>{_x(tr("contents", md.language))}</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body>'
               f'<nav epub:type="toc" id="toc"><h1>{_x(tr("contents", md.language))}</h1><ol>{toc_items}</ol></nav>{landmarks}</body></html>')
    manifest[0].data = nav_doc.encode("utf-8")

    counter = [0]

    def ncx_point(n: _Nav) -> str:
        counter[0] += 1
        pid = counter[0]
        kids = "".join(ncx_point(c) for c in n.children)
        return (f'<navPoint id="np{pid}" playOrder="{pid}"><navLabel><text>{_x(n.title)}</text></navLabel>'
                f'<content src={_attr("text/" + n.href)}/>{kids}</navPoint>')

    points = "".join(ncx_point(n) for n in navs)
    ncx = (f'<?xml version="1.0" encoding="utf-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
           f'<head><meta name="dtb:uid" content={_attr(uid)}/><meta name="dtb:depth" content="2"/>'
           f'<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>'
           f'<docTitle><text>{_x(md.title)}</text></docTitle><navMap>{points}</navMap></ncx>')
    manifest[1].data = ncx.encode("utf-8")

    meta = [f'<dc:identifier id="bookid">{_x(uid)}</dc:identifier>', f"<dc:title>{_x(md.title)}</dc:title>",
            f"<dc:language>{_x(md.language or 'en')}</dc:language>"]
    if md.author:
        meta.append(f"<dc:creator>{_x(md.author)}</dc:creator>")
    if md.publisher:
        meta.append(f"<dc:publisher>{_x(md.publisher)}</dc:publisher>")
    if md.description:
        meta.append(f"<dc:description>{_x(md.description)}</dc:description>")
    if md.rights:
        meta.append(f"<dc:rights>{_x(md.rights)}</dc:rights>")
    if md.isbn:
        meta.append(f"<dc:source>ISBN {_x(md.isbn)}</dc:source>")
    meta.append(f'<meta property="dcterms:modified">{now}</meta>')
    if cover:
        meta.append('<meta name="cover" content="cover-img"/>')
    man_xml = "".join(
        f'<item id="{i.id}" href={_attr(i.href)} media-type="{i.media}"' + (f' properties="{i.props}"' if i.props else "") + "/>"
        for i in manifest)
    spine_ids = [i.id for i in front] + [i.id for i in body_items]
    spine = "".join(f'<itemref idref="{i}"/>' for i in spine_ids)
    opf = (f'<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
           f'unique-identifier="bookid" xml:lang="{_x(md.language or "en")}"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           f'{"".join(meta)}</metadata><manifest>{man_xml}</manifest><spine toc="ncx">{spine}</spine></package>')
    container = ('<?xml version="1.0" encoding="utf-8"?>\n<container version="1.0" '
                 'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                 '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                 '</rootfiles></container>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        for it in manifest:
            z.writestr(f"OEBPS/{it.href}", it.data, compress_type=zipfile.ZIP_DEFLATED)
    bld.notes.append("Reflowable EPUB 3: page numbers, running headers and print margins do not apply; "
                     "checked structurally, not with the W3C EpubCheck tool")
    return sorted(set(bld.notes))
