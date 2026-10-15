"""Template library: JSON templates stored outside the application code."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from ..domain.book import BookProject
from ..domain.content_blocks import HeadingBlock, ParagraphBlock, Run
from ..domain.layouts import Margins
from ..domain.sections import Section
from ..domain.styles import merge_template_styles
from .app_paths import builtin_templates_dir, user_templates_dir

# Settings a template may control. Cover, export profile and metadata are never touched.
TEMPLATE_SETTING_KEYS = {
    "page_size", "width_mm", "height_mm", "landscape", "margins", "mirrored_margins",
    "facing_pages", "matter_margins", "body_font", "body_size", "line_height",
    "paragraph_spacing", "first_line_indent", "justify", "widow_lines", "orphan_lines",
    "chapter_new_page", "chapter_right_page", "chapter_drop", "show_toc", "toc_depth",
    "toc_page_numbers", "front_numbering", "header_verso", "header_recto", "footer",
    "footer_position", "header_rule", "image_default_width_pct",
}


class TemplateError(Exception):
    pass


class TemplateService:
    def __init__(self, builtin_dir: Path | None = None, user_dir: Path | None = None):
        self.builtin_dir = builtin_dir or builtin_templates_dir()
        self.user_dir = user_dir or user_templates_dir()

    # -- listing ----------------------------------------------------------
    def _read(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise TemplateError(f"Cannot read template {path.name}: {e}") from e
        if not isinstance(data, dict) or "key" not in data or "settings" not in data:
            raise TemplateError(f"{path.name} is not a valid template")
        return data

    def list_templates(self) -> list[dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for d, builtin in ((self.builtin_dir, True), (self.user_dir, False)):
            if not d.exists():
                continue
            for p in sorted(d.glob("*.json")):
                try:
                    t = self._read(p)
                except TemplateError:
                    continue
                t["builtin"] = builtin and not t.get("overrides_builtin")
                t["source"] = "built-in" if builtin else "user"
                out[t["key"]] = t  # user templates override built-ins with the same key
        return list(out.values())

    def get(self, key: str) -> dict[str, Any]:
        for t in self.list_templates():
            if t["key"] == key:
                return t
        raise TemplateError(f"Unknown template '{key}'")

    # -- user operations ----------------------------------------------------
    @staticmethod
    def _slug(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "template"

    def duplicate(self, key: str, new_name: str) -> dict[str, Any]:
        t = json.loads(json.dumps(self.get(key)))
        new_key = self._slug(new_name)
        existing = {x["key"] for x in self.list_templates()}
        base, n = new_key, 2
        while new_key in existing:
            new_key = f"{base}_{n}"
            n += 1
        t.update(key=new_key, name=new_name, builtin=False)
        t.pop("source", None)
        self.save_user(t)
        return t

    def save_user(self, template: dict[str, Any]) -> Path:
        template = {k: v for k, v in template.items() if k not in ("source",)}
        template["builtin"] = False
        path = self.user_dir / f"{template['key']}.json"
        path.write_text(json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def customise_builtin(self, key: str, template: dict[str, Any]) -> None:
        t = dict(template)
        t["key"] = key
        t["overrides_builtin"] = True
        self.save_user(t)

    def reset(self, key: str) -> bool:
        """Remove the user's override of a built-in template. Returns True if one existed."""
        path = self.user_dir / f"{key}.json"
        if path.exists() and (self.builtin_dir / f"{key}.json").exists():
            path.unlink()
            return True
        return False

    def delete_user(self, key: str) -> None:
        path = self.user_dir / f"{key}.json"
        if not path.exists():
            raise TemplateError("Only user templates can be deleted")
        path.unlink()

    def export_template(self, key: str, dest: Path) -> None:
        t = self.get(key)
        t = {k: v for k, v in t.items() if k != "source"}
        Path(dest).write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_template(self, src: Path) -> dict[str, Any]:
        t = self._read(Path(src))
        if self._slug(t["key"]) != t["key"]:
            t["key"] = self._slug(t["key"])
        existing = {x["key"] for x in self.list_templates()}
        if t["key"] in existing:
            t["key"] = self._slug(t["key"] + "_imported")
        t["builtin"] = False
        t.pop("overrides_builtin", None)
        self.save_user(t)
        return t


def apply_template(book: BookProject, template: dict[str, Any],
                   preserve_customised_styles: bool = True,
                   apply_page_setup: bool = True) -> list[str]:
    """Apply a template to a book. Returns the names of styles that were kept as customised."""
    settings = book.settings
    for k, v in template.get("settings", {}).items():
        if k not in TEMPLATE_SETTING_KEYS:
            continue
        if not apply_page_setup and k in ("page_size", "width_mm", "height_mm", "landscape",
                                          "margins", "matter_margins"):
            continue
        if k == "margins":
            v = Margins.from_dict(v)
        setattr(settings, k, v)
    settings.template = template["key"]
    kept = [n for n in template.get("styles", {})
            if book.styles.get(n) and book.styles[n].user_modified and preserve_customised_styles]
    book.styles = merge_template_styles(book.styles, template.get("styles", {}),
                                        preserve_customised_styles)
    return kept


def sample_book(template: dict[str, Any]) -> BookProject:
    """A small book used for the template preview."""
    book = BookProject()
    book.metadata.title = template.get("name", "Sample")
    book.metadata.author = "Author Name"
    apply_template(book, template, preserve_customised_styles=False)
    ch = Section("A Sample Chapter", "chapter")
    text = ("The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor "
            "jugs. Ștefan își ține ceaiul în căni țesute. ") * 4
    ch.blocks = [ParagraphBlock(runs=[Run(text)]),
                 HeadingBlock(level=1, runs=[Run("A Section Heading")]),
                 ParagraphBlock(runs=[Run(text)]), ParagraphBlock(runs=[Run(text)])]
    book.sections = [ch]
    return book
