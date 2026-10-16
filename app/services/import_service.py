"""Import orchestration: thread-safe parsing followed by a main-thread commit."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from ..domain.book import MAX_IMAGE_PIXELS, Asset, BookProject
from ..domain.content_blocks import ImageBlock, RecipeBlock, new_id
from ..domain.sections import BACK_KINDS, Section
from ..importers.base import (MAX_IMPORT_BYTES, ImportFailure, ImportOptions, ImportReport,
                              ImportResult)
from ..importers.docx_importer import import_docx
from ..importers.html_importer import import_html
from ..importers.markdown_importer import import_markdown
from ..importers.pdf_importer import import_pdf
from ..importers.txt_importer import import_txt
from ..persistence.project_archive import MAX_SOURCE_SNAPSHOT
from .language_detect import detect_language

IMPORTERS = {
    ".docx": import_docx, ".txt": import_txt, ".text": import_txt,
    ".md": import_markdown, ".markdown": import_markdown,
    ".html": import_html, ".htm": import_html, ".pdf": import_pdf,
}
SUPPORTED_EXTENSIONS = sorted(IMPORTERS)
FILE_FILTER = ("Manuscripts (*.docx *.txt *.md *.markdown *.html *.htm *.pdf);;"
               "Word (*.docx);;Text (*.txt);;Markdown (*.md *.markdown);;HTML (*.html *.htm);;"
               "PDF reference (*.pdf);;All files (*.*)")


@dataclass
class StagedImport:
    result: ImportResult
    assets: dict[str, Asset] = field(default_factory=dict)
    raw: bytes = b""
    source_name: str = ""


class _Staging:
    def __init__(self, report: ImportReport):
        self.assets: dict[str, Asset] = {}
        self.report = report

    def add(self, data: bytes, filename: str) -> str | None:
        digest = hashlib.sha256(data).hexdigest()
        for a in self.assets.values():
            if a.sha256 == digest:
                return a.id
        try:
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                if w * h > MAX_IMAGE_PIXELS:
                    self.report.add("warning", f"Image '{filename}' is too large and was skipped")
                    return None
                im.verify()
        except Exception:
            self.report.add("warning", f"Image '{filename}' is not a readable image and was skipped")
            return None
        a = Asset(id=new_id(), filename=filename, data=data, width=w, height=h, sha256=digest)
        self.assets[a.id] = a
        return a.id


def run_import(path: Path, options: ImportOptions | None = None) -> StagedImport:
    """Parse a file. Reads the source but never writes to it. Safe to call off the UI thread."""
    options = options or ImportOptions()
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".rtf":
        raise ImportFailure("RTF import is not available: no reliable offline RTF parser is "
                            "bundled. Save the document as DOCX or TXT and import that.")
    importer = IMPORTERS.get(ext)
    if importer is None:
        raise ImportFailure(f"Unsupported file type '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    try:
        size = path.stat().st_size
        if size > MAX_IMPORT_BYTES:
            raise ImportFailure("The file is too large to import")
        raw = path.read_bytes()
    except OSError as e:
        raise ImportFailure(f"The file could not be read: {e}") from e
    holder: list[_Staging] = []

    def sink(data: bytes, name: str) -> str | None:
        return holder[0].add(data, name)

    # Importers create their own report; stage assets against a placeholder first.
    holder.append(_Staging(ImportReport()))
    result = importer(path, raw, options, sink)
    holder[0].report = result.report
    sample = " ".join(b.plain_text() for s in result.sections for b in s.blocks[:300])[:60000]
    result.language = detect_language(sample)
    if result.language:
        result.report.add("info", f"Language of the text detected as '{result.language}' (used for quotes, "
                                  "hyphenation and generated labels; change it in Book properties)")
    return StagedImport(result, holder[0].assets, raw, path.name)


def _remap_assets(section: Section, mapping: dict[str, str]) -> None:
    for s in section.walk():
        for b in s.blocks:
            if isinstance(b, ImageBlock) and b.asset in mapping:
                b.asset = mapping[b.asset]
            elif isinstance(b, RecipeBlock) and b.image in mapping:
                b.image = mapping[b.image]


def commit_import(book: BookProject, staged: StagedImport, options: ImportOptions | None = None,
                  insert_at: int | None = None) -> list[Section]:
    """Merge a parsed import into the project (main thread)."""
    options = options or ImportOptions()
    mapping: dict[str, str] = {}
    for a in staged.assets.values():
        existing = next((x for x in book.assets.values() if x.sha256 == a.sha256), None)
        if existing:
            mapping[a.id] = existing.id
        else:
            book.assets[a.id] = a
    sections = staged.result.sections
    for s in sections:
        _remap_assets(s, mapping)
    if insert_at is None:
        insert_at = next((i for i, s in enumerate(book.sections) if s.kind in BACK_KINDS),
                         len(book.sections))
    for offset, s in enumerate(sections):
        book.sections.insert(insert_at + offset, s)
    # Original-content snapshot, never modified afterwards.
    if staged.raw and len(staged.raw) <= MAX_SOURCE_SNAPSHOT:
        name = staged.source_name
        n = 1
        while name in book.sources:
            n += 1
            name = f"{n}_{staged.source_name}"
        book.sources[name] = staged.raw
    else:
        staged.result.report.add("info", "Original file was too large for a snapshot in the project")
    if options.update_metadata and staged.result.title and book.metadata.title in ("", "Untitled Book"):
        book.metadata.title = staged.result.title
    book.import_reports.append(staged.result.report.to_dict())
    return sections


def import_file(book: BookProject, path: Path, options: ImportOptions | None = None) -> ImportResult:
    staged = run_import(path, options)
    commit_import(book, staged, options)
    return staged.result
