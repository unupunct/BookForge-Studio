"""The central, UI- and renderer-independent document model."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from .content_blocks import Block, new_id
from .layouts import BookSettings
from .metadata import BookMetadata
from .sections import Section
from .styles import StyleDefinition, default_styles

SCHEMA_VERSION = 1
MAX_IMAGE_PIXELS = 120_000_000  # decompression-bomb guard for imported images


@dataclass
class Asset:
    """A binary resource (image) owned by the project."""

    id: str
    filename: str
    data: bytes = field(repr=False, default=b"")
    width: int = 0
    height: int = 0
    sha256: str = ""
    source_path: str = ""  # informational only, never used to locate the asset

    @property
    def archive_path(self) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", self.filename)[:80] or "asset"
        return f"assets/{self.id}_{safe}"

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "filename": self.filename, "path": self.archive_path,
                "width": self.width, "height": self.height, "sha256": self.sha256,
                "source_path": self.source_path}


@dataclass
class BookProject:
    metadata: BookMetadata = field(default_factory=BookMetadata)
    settings: BookSettings = field(default_factory=BookSettings)
    styles: dict[str, StyleDefinition] = field(default_factory=default_styles)
    sections: list[Section] = field(default_factory=list)
    assets: dict[str, Asset] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    # Original-content snapshots kept for provenance: archive name -> bytes
    sources: dict[str, bytes] = field(default_factory=dict, repr=False)
    import_reports: list[dict[str, Any]] = field(default_factory=list)

    # -- structure queries -------------------------------------------------
    def walk(self) -> Iterator[Section]:
        for s in self.sections:
            yield from s.walk()

    def find_section(self, section_id: str) -> Section | None:
        return next((s for s in self.walk() if s.id == section_id), None)

    def find_parent(self, section_id: str) -> tuple[list[Section], int] | None:
        """Return (sibling list, index) containing the section."""
        def rec(siblings: list[Section]) -> tuple[list[Section], int] | None:
            for i, s in enumerate(siblings):
                if s.id == section_id:
                    return siblings, i
                found = rec(s.children)
                if found:
                    return found
            return None
        return rec(self.sections)

    def find_block(self, block_id: str) -> tuple[Section, Block] | None:
        for s in self.walk():
            for b in s.blocks:
                if b.id == block_id:
                    return s, b
        return None

    # -- structure edits ---------------------------------------------------
    def add_section(self, section: Section, parent_id: str | None = None,
                    index: int | None = None) -> Section:
        siblings = self.sections
        if parent_id:
            parent = self.find_section(parent_id)
            if parent is None:
                raise KeyError(f"No section {parent_id}")
            siblings = parent.children
        if index is None or index > len(siblings):
            siblings.append(section)
        else:
            siblings.insert(max(index, 0), section)
        return section

    def remove_section(self, section_id: str) -> Section:
        loc = self.find_parent(section_id)
        if loc is None:
            raise KeyError(f"No section {section_id}")
        siblings, i = loc
        return siblings.pop(i)

    def move_section(self, section_id: str, new_parent_id: str | None, index: int) -> None:
        sec = self.find_section(section_id)
        if sec is None:
            raise KeyError(section_id)
        if new_parent_id and any(s.id == new_parent_id for s in sec.walk()):
            raise ValueError("Cannot move a section into itself or its descendants")
        removed = self.remove_section(section_id)
        self.add_section(removed, new_parent_id, index)

    def duplicate_section(self, section_id: str) -> Section:
        loc = self.find_parent(section_id)
        if loc is None:
            raise KeyError(section_id)
        siblings, i = loc
        copy = siblings[i].clone()
        copy.title = f"{copy.title} (copy)"
        siblings.insert(i + 1, copy)
        return copy

    def move_up_down(self, section_id: str, delta: int) -> bool:
        loc = self.find_parent(section_id)
        if loc is None:
            return False
        siblings, i = loc
        j = i + delta
        if not 0 <= j < len(siblings):
            return False
        siblings[i], siblings[j] = siblings[j], siblings[i]
        return True

    # -- assets ------------------------------------------------------------
    def add_asset(self, data: bytes, filename: str, source_path: str = "") -> Asset:
        from PIL import Image
        import io
        digest = hashlib.sha256(data).hexdigest()
        for a in self.assets.values():  # de-duplicate identical files
            if a.sha256 == digest:
                return a
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w * h > MAX_IMAGE_PIXELS:
                raise ValueError(f"Image {filename} is too large ({w}x{h} pixels)")
            im.verify()
        asset = Asset(id=new_id(), filename=filename, data=data, width=w, height=h,
                      sha256=digest, source_path=source_path)
        self.assets[asset.id] = asset
        return asset

    # -- statistics --------------------------------------------------------
    def all_text_blocks(self) -> Iterator[tuple[Section, Block]]:
        for s in self.walk():
            if s.enabled:
                for b in s.blocks:
                    yield s, b

    def word_count(self, section: Section | None = None) -> int:
        n = 0
        if section is not None:
            return sum(len(b.plain_text().split()) for b in section.blocks)
        for _, b in self.all_text_blocks():
            n += len(b.plain_text().split())
        return n

    def char_count(self, section: Section | None = None) -> int:
        if section is not None:
            return sum(len(b.plain_text()) for b in section.blocks)
        return sum(len(b.plain_text()) for _, b in self.all_text_blocks())

    # -- serialisation -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "metadata": self.metadata.to_dict(),
            "settings": self.settings.to_dict(),
            "styles": {k: v.to_dict() for k, v in self.styles.items()},
            "sections": [s.to_dict() for s in self.sections],
            "assets": [a.to_dict() for a in self.assets.values()],
            "import_reports": self.import_reports,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BookProject":
        styles = default_styles()
        for k, v in d.get("styles", {}).items():
            styles[k] = StyleDefinition.from_dict({**v, "name": k})
        p = cls(
            metadata=BookMetadata.from_dict(d.get("metadata", {})),
            settings=BookSettings.from_dict(d.get("settings", {})),
            styles=styles,
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            id=d.get("id") or new_id(),
            import_reports=d.get("import_reports", []),
        )
        # Asset binaries are attached by the persistence layer.
        for a in d.get("assets", []):
            p.assets[a["id"]] = Asset(id=a["id"], filename=a.get("filename", "asset"),
                                      width=a.get("width", 0), height=a.get("height", 0),
                                      sha256=a.get("sha256", ""),
                                      source_path=a.get("source_path", ""))
        return p

    def structure_snapshot(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.sections]

    def restore_structure(self, snap: list[dict[str, Any]]) -> None:
        self.sections = [Section.from_dict(s) for s in snap]
