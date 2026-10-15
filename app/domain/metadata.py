"""Book metadata."""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass
class BookMetadata:
    title: str = "Untitled Book"
    subtitle: str = ""
    author: str = ""
    language: str = "en"
    category: str = "custom"
    publisher: str = ""
    isbn: str = ""
    year: str = ""
    description: str = ""
    rights: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BookMetadata":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})
