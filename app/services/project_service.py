"""Creating projects from book profiles, recent files and application settings."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.book import BookProject
from ..domain.content_blocks import ExerciseBlock, HeadingBlock, ParagraphBlock, Run
from ..domain.layouts import PAGE_SIZES
from ..domain.sections import Section
from .app_paths import user_data_dir
from .template_service import TemplateError, TemplateService, apply_template


@dataclass(frozen=True)
class BookProfile:
    key: str
    label: str
    template: str
    description: str
    chapter_title: str = "Chapter 1"
    toc: bool = True
    extra_front: tuple[str, ...] = ()
    extra_back: tuple[str, ...] = ()


# Profiles set sensible defaults, never limits: everything remains editable afterwards.
PROFILES: dict[str, BookProfile] = {p.key: p for p in [
    BookProfile("novel", "Novel", "modern_novel", "Readable body text, consistent chapter openings.",
                "Chapter 1", True, ("dedication",), ("acknowledgments",)),
    BookProfile("nonfiction", "Nonfiction", "business_nonfiction", "Headings, quotations and notes.",
                "Introduction", True, ("preface",), ("bibliography", "index")),
    BookProfile("poetry", "Poetry", "minimalist_poetry", "Line breaks and stanzas are preserved.",
                "Poems", False, ("dedication",), ()),
    BookProfile("technical", "Technical manual", "technical_handbook",
                "Heading hierarchy, code blocks, tables and references.", "Getting started", True,
                ("preface",), ("appendix", "glossary", "index")),
    BookProfile("textbook", "Textbook", "academic_textbook",
                "Learning objectives, exercises, examples and references.", "Chapter 1", True,
                ("preface",), ("glossary", "bibliography", "index")),
    BookProfile("children", "Children's book", "illustrated_children",
                "Large type and image-led pages.", "Story", False, (), ()),
    BookProfile("illustrated", "Illustrated book", "photo_heavy", "Image-forward layouts.",
                "Chapter 1", True, (), ()),
    BookProfile("cookbook", "Cookbook", "cookbook", "Structured recipes with times and servings.",
                "Recipes", True, ("preface",), ("index",)),
    BookProfile("biography", "Biography", "biography", "Reflective chapters with notes.",
                "Chapter 1", True, ("foreword",), ("acknowledgments", "index")),
    BookProfile("custom", "Custom book", "general_purpose", "Start from general-purpose defaults.",
                "Chapter 1", True, (), ()),
]}


@dataclass
class NewBookSpec:
    title: str = "Untitled Book"
    subtitle: str = ""
    author: str = ""
    language: str = "en"
    profile: str = "custom"
    output: str = "digital"  # digital | print | both
    page_size: str | None = None  # None -> template default
    template: str | None = None  # None -> profile default
    cover: bool = True
    toc: bool = True
    chapters_new_page: bool = True


def create_project(spec: NewBookSpec, templates: TemplateService | None = None) -> BookProject:
    templates = templates or TemplateService()
    profile = PROFILES.get(spec.profile, PROFILES["custom"])
    book = BookProject()
    md = book.metadata
    md.title, md.subtitle, md.author = spec.title.strip() or "Untitled Book", spec.subtitle.strip(), spec.author.strip()
    md.language, md.category = spec.language, profile.key
    try:
        tpl = templates.get(spec.template or profile.template)
        apply_template(book, tpl, preserve_customised_styles=False)
    except TemplateError:
        pass  # fall back to model defaults rather than blocking project creation
    if spec.page_size and spec.page_size in PAGE_SIZES:
        book.settings.set_page_size(spec.page_size)
    st = book.settings
    st.chapter_new_page = spec.chapters_new_page
    st.show_toc = spec.toc
    st.export_profile = "print" if spec.output == "print" else "digital"
    st.cover.enabled = spec.cover

    secs: list[Section] = []
    if spec.cover:
        secs.append(Section("Front cover", "front_cover", in_toc=False))
    secs.append(Section("Title page", "title_page", in_toc=False, show_title=False))
    secs.append(Section("Copyright", "copyright", in_toc=False, show_title=False))
    for k in profile.extra_front:
        secs.append(Section({"dedication": "Dedication", "preface": "Preface",
                             "foreword": "Foreword"}[k], k, enabled=(k != "dedication")))
    if spec.toc and profile.toc:
        secs.append(Section("Contents", "toc", in_toc=False))
    chapter = Section(profile.chapter_title, "chapter")
    chapter.blocks = _starter_blocks(profile.key)
    secs.append(chapter)
    for k in profile.extra_back:
        label = {"acknowledgments": "Acknowledgments", "bibliography": "Bibliography",
                 "index": "Index", "appendix": "Appendix", "glossary": "Glossary"}[k]
        secs.append(Section(label, k, enabled=False))  # optional sections start disabled
    if spec.cover:
        secs.append(Section("Back cover", "back_cover", in_toc=False))
    book.sections = secs
    return book


def _starter_blocks(profile: str):
    if profile == "textbook":
        return [ExerciseBlock(kind="objective", title="Learning objectives",
                              runs=[Run("State what the reader will be able to do.")]),
                ParagraphBlock(runs=[])]
    if profile == "poetry":
        from ..domain.content_blocks import PoetryBlock
        return [PoetryBlock(title="Untitled", text="")]
    return [ParagraphBlock(runs=[])]


# ---------------------------------------------------------------- settings
@dataclass
class AppSettings:
    autosave_seconds: int = 60
    recent: list[str] = field(default_factory=list)
    last_open_dir: str = ""
    last_export_dir: str = ""
    ui_scale: float = 1.0
    max_recent: int = 12


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (user_data_dir() / "settings.json")
        self.data = AppSettings()
        self.load()

    def load(self) -> None:
        try:
            raw: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in raw.items():
                if hasattr(self.data, k):
                    setattr(self.data, k, v)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data.__dict__, indent=2), encoding="utf-8")
        except OSError:
            pass

    def add_recent(self, path: Path) -> None:
        p = str(Path(path).resolve())
        self.data.recent = [p] + [r for r in self.data.recent if r != p]
        self.data.recent = self.data.recent[: self.data.max_recent]
        self.save()

    def existing_recent(self) -> list[str]:
        return [r for r in self.data.recent if Path(r).exists()]


def create_from_manuscript(spec: NewBookSpec, staged, options, templates: TemplateService | None = None):
    """A ready-to-export book from one parsed manuscript: template + front matter + the text.

    Title and author are taken from the document when the spec leaves them empty.
    """
    from .import_service import commit_import
    book = create_project(spec, templates)
    book.sections = [s for s in book.sections if s.kind != "chapter"]  # drop the empty starter chapter
    new_sections = commit_import(book, staged, options)
    res = staged.result
    if spec.title.strip() in ("", "Untitled Book") and res.title:
        book.metadata.title = res.title
    if not book.metadata.author and getattr(res, "author", None):
        book.metadata.author = res.author
    md = book.metadata
    if not any(v.strip() for v in (md.author, md.rights, md.publisher, md.isbn, md.year)):
        for s in book.sections:  # nothing to print: no blank copyright page (enable it once details exist)
            if s.kind == "copyright":
                s.enabled = False
    chapters = [s for s in new_sections if s.kind == "chapter"]
    if len(chapters) == 1 and chapters[0].title.strip().lower() == book.metadata.title.strip().lower():
        chapters[0].show_title = False  # the title page already carries the book's name
    if getattr(res, "subtitle", None) and not book.metadata.subtitle:
        book.metadata.subtitle = res.subtitle
    if getattr(res, "description", None) and not book.metadata.description:
        book.metadata.description = res.description
    return book
