"""Book validation: structure, assets, fonts, images and layout problems."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.book import BookProject
from ..domain.content_blocks import (CodeBlock, ExerciseBlock, HeadingBlock, ImageBlock,
                                     PoetryBlock, RecipeBlock, plain_runs)
from ..domain.layouts import MM_TO_PT
from ..domain.sections import GENERATED_KINDS
from ..layout.model import ImageItem, LayoutResult
from ..layout.page_builder import content_size
from ..layout.typography import fonts
from .image_service import effective_dpi


@dataclass
class ValidationIssue:
    severity: str  # error | warning | info
    code: str
    message: str
    section_id: str | None = None
    block_id: str | None = None
    page_index: int | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str, **kw) -> None:
        self.issues.append(ValidationIssue(severity, code, message, **kw))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (f"{len(self.errors)} error(s), {len(self.warnings)} warning(s), "
                f"{len([i for i in self.issues if i.severity == 'info'])} note(s)")


MIN_DPI = {"digital": (72, 110), "proof": (0, 0), "print": (150, 250)}  # (error below, warn below)


def validate_book(book: BookProject, layout: LayoutResult | None = None,
                  profile: str = "digital") -> ValidationReport:
    rep = ValidationReport()
    md = book.metadata
    st = book.settings
    if not md.title.strip() or md.title == "Untitled Book":
        rep.add("warning", "no_title", "The book still has the default title")
    if not md.author.strip():
        rep.add("info", "no_author", "No author is set")

    chapters = [s for s in book.walk() if s.enabled and s.kind not in GENERATED_KINDS]
    if not chapters:
        rep.add("error", "empty_book", "The book has no enabled content sections")
    for s in book.walk():
        if s.enabled and s.kind in ("chapter", "section", "part") and not s.blocks and not s.children:
            rep.add("warning", "empty_section", f"'{s.title or s.kind}' has no content",
                    section_id=s.id)

    w, h = content_size(st, "main")
    if w < 100 or h < 150:
        rep.add("error", "tiny_text_area",
                f"The text area ({w / MM_TO_PT:.0f} x {h / MM_TO_PT:.0f} mm) is too small for a book page")

    # assets
    for s in book.walk():
        if not s.enabled:
            continue
        for b in s.blocks:
            if isinstance(b, ImageBlock):
                a = book.assets.get(b.asset)
                if a is None or not a.data:
                    rep.add("error", "missing_asset",
                            f"Image in '{s.title}' cannot be found (relink or remove it)",
                            section_id=s.id, block_id=b.id)
                elif not b.alt.strip():
                    rep.add("info", "no_alt_text", f"Image in '{s.title}' has no alternative text",
                            section_id=s.id, block_id=b.id)
    cov = book.settings.cover
    if cov.image_asset and (cov.image_asset not in book.assets or not book.assets[cov.image_asset].data):
        rep.add("error", "missing_cover_image", "The cover image file is missing")

    _check_glyphs(book, rep)

    if layout is not None:
        counts: dict[str, list] = {}
        for i in layout.issues:
            if i.severity == "info" and i.code in ("poem_continues", "code_wrapped", "poem_page", "poem_tightened"):
                counts.setdefault(i.code, []).append(i)
        for code, items in counts.items():
            if len(items) > 3:  # one summary instead of hundreds of identical notes
                rep.add("info", code, f"{len(items)} × {items[0].message.lower()}",
                        page_index=items[0].page_index, block_id=items[0].block_id)
        for i in layout.issues:
            if i.code in counts and len(counts[i.code]) > 3:
                continue
            if i.code in ("overflow", "missing_asset", "layout_loop"):
                sev = "error"
            elif i.code in ("accidental_blank_page", "image_scaled"):
                sev = "warning"
            else:
                sev = i.severity
            if i.code == "missing_asset":
                continue  # already reported with section context above
            rep.add(sev, i.code, i.message, section_id=i.section_id, block_id=i.block_id,
                    page_index=i.page_index)
        err_below, warn_below = MIN_DPI.get(profile, MIN_DPI["digital"])
        for p in layout.pages:
            for it in p.items:
                if isinstance(it, ImageItem) and not it.missing:
                    a = book.assets.get(it.asset_id)
                    if not a or not a.data:
                        continue
                    dpi = effective_dpi(a, it.w, it.crop)
                    if dpi < err_below:
                        rep.add("error", "low_resolution",
                                f"Image on page {p.index + 1} is only {dpi:.0f} dpi at its printed size",
                                block_id=it.block_id, page_index=p.index)
                    elif dpi < warn_below:
                        rep.add("warning", "low_resolution",
                                f"Image on page {p.index + 1} is {dpi:.0f} dpi; "
                                f"{warn_below}+ dpi is recommended for this output",
                                block_id=it.block_id, page_index=p.index)
    return rep


def _check_glyphs(book: BookProject, rep: ValidationReport) -> None:
    """Warn when a selected font cannot draw characters used by the text."""
    st = book.settings
    for s in book.walk():
        if not s.enabled:
            continue
        body_text: list[str] = [s.title]
        code_text: list[str] = []
        first_block: dict[str, str | None] = {"body": None, "mono": None}
        for b in s.blocks:
            if isinstance(b, CodeBlock):
                code_text.append(b.text)
                first_block["mono"] = first_block["mono"] or b.id
            else:
                t = b.plain_text()
                if t:
                    body_text.append(t)
                    first_block["body"] = first_block["body"] or b.id
        for fam, texts, key in ((st.body_font, body_text, "body"), ("mono", code_text, "mono")):
            if not texts:
                continue
            try:
                missing = fonts.missing_glyphs(fam, "".join(texts))
            except Exception as e:  # font problems must not break validation
                rep.add("warning", "font_unavailable", f"Font '{fam}' could not be loaded: {e}")
                return
            if missing:
                shown = " ".join(sorted(missing)[:12])
                rep.add("warning", "missing_glyphs",
                        f"Font '{fam}' lacks glyphs used in '{s.title}': {shown}",
                        section_id=s.id, block_id=first_block[key])
