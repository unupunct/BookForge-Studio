"""Structural checks of an EPUB package (not a replacement for the W3C EpubCheck tool).

Verifies what readers rely on: stored `mimetype` first, container -> package document, manifest files
present, spine references, well-formed XHTML, a navigation document, and that every relative link or image
target (and fragment id) in the content documents exists.
"""
from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path
from urllib.parse import unquote, urldefrag

from lxml import etree

NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "o": "http://www.idpf.org/2007/opf",
      "h": "http://www.w3.org/1999/xhtml", "e": "http://www.idpf.org/2007/ops",
      "n": "http://www.daisy.org/z3986/2005/ncx/"}


def check_epub(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        return [f"not a ZIP archive: {e}"]
    with z:
        names = z.namelist()
        if not names or names[0] != "mimetype":
            problems.append("'mimetype' must be the first entry")
        else:
            info = z.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                problems.append("'mimetype' must be stored without compression")
            if z.read("mimetype") != b"application/epub+zip":
                problems.append("'mimetype' has the wrong content")
        try:
            container = etree.fromstring(z.read("META-INF/container.xml"))
            opf_path = container.find(".//c:rootfile", NS).get("full-path")
            opf = etree.fromstring(z.read(opf_path))
        except (KeyError, etree.XMLSyntaxError, AttributeError) as e:
            return problems + [f"container/package document unreadable: {e}"]
        base = posixpath.dirname(opf_path)
        manifest = {}
        for it in opf.findall(".//o:manifest/o:item", NS):
            href = posixpath.normpath(posixpath.join(base, unquote(it.get("href"))))
            manifest[it.get("id")] = (href, it.get("media-type"), it.get("properties") or "")
            if href not in names:
                problems.append(f"manifest item '{it.get('id')}' missing from the archive: {href}")
        for ref in opf.findall(".//o:spine/o:itemref", NS):
            if ref.get("idref") not in manifest:
                problems.append(f"spine item '{ref.get('idref')}' is not in the manifest")
        for req in ("dc:identifier", "dc:title", "dc:language"):
            tag = "{http://purl.org/dc/elements/1.1/}" + req.split(":")[1]
            if opf.find(f".//{tag}") is None:
                problems.append(f"package metadata lacks {req}")
        if opf.find(".//o:meta[@property='dcterms:modified']", NS) is None:
            problems.append("package metadata lacks dcterms:modified")
        navs = [h for h, m, p in manifest.values() if "nav" in p.split()]
        if len(navs) != 1:
            problems.append("exactly one manifest item must have properties='nav'")
        ids: dict[str, set[str]] = {}
        docs: dict[str, etree._Element] = {}
        for href, media, _ in manifest.values():
            if media == "application/xhtml+xml" and href in names:
                try:
                    root = etree.fromstring(z.read(href))
                except etree.XMLSyntaxError as e:
                    problems.append(f"{href} is not well-formed XML: {e}")
                    continue
                docs[href] = root
                ids[href] = {el.get("id") for el in root.iter() if el.get("id")}
        if navs and navs[0] in docs:
            if not docs[navs[0]].xpath("//h:nav[@e:type='toc']", namespaces=NS):
                problems.append("navigation document has no nav epub:type='toc'")
        for href, root in docs.items():
            folder = posixpath.dirname(href)
            for el in root.iter():
                for attr in ("href", "src"):
                    val = el.get(attr)
                    if not val or val.startswith(("http:", "https:", "mailto:", "data:")):
                        continue
                    target, frag = urldefrag(val)
                    tpath = href if not target else posixpath.normpath(posixpath.join(folder, unquote(target)))
                    if tpath not in names:
                        problems.append(f"{href}: {attr}='{val}' points to a missing file")
                    elif frag and tpath in ids and frag not in ids[tpath]:
                        problems.append(f"{href}: link '{val}' points to a missing id")
        # NCX
        for href, media, _ in manifest.values():
            if media == "application/x-dtbncx+xml" and href in names:
                try:
                    ncx = etree.fromstring(z.read(href))
                    for c in ncx.iter("{%s}content" % NS["n"]):
                        target, frag = urldefrag(c.get("src"))
                        tpath = posixpath.normpath(posixpath.join(posixpath.dirname(href), target))
                        if tpath not in names or (frag and tpath in ids and frag not in ids[tpath]):
                            problems.append(f"toc.ncx entry '{c.get('src')}' does not resolve")
                except etree.XMLSyntaxError as e:
                    problems.append(f"toc.ncx is not well-formed: {e}")
        for name in names:
            if name.endswith("/") or name.startswith(("META-INF/", "mimetype")):
                continue
            rel = posixpath.relpath(name, base) if base else name
            if rel not in {posixpath.relpath(h, base) if base else h for h, _, _ in manifest.values()} and \
                    not name.endswith("content.opf"):
                problems.append(f"file not listed in the manifest: {name}")
    return problems
