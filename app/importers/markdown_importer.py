"""Markdown import using markdown-it-py (CommonMark + tables)."""
from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token

from ..domain.content_blocks import (Block, CodeBlock, HeadingBlock, ImageBlock, ListBlock,
                                     ParagraphBlock, QuoteBlock, Run, SceneBreakBlock,
                                     TableBlock, merge_runs, runs_text)
from ..domain.sections import Section
from .base import (ImageSink, ImportFailure, ImportOptions, ImportReport, ImportResult,
                   split_into_sections, stem_title)
from .postprocess import SOFT, finish_text_blocks, promote_chapter_headings
from .txt_importer import decode_text


def load_local_image(src: str, base: Path | None, sink: ImageSink, report: ImportReport) -> str | None:
    """Resolve an image reference without ever leaving the document's folder."""
    if src.startswith(("http://", "https://", "//", "ftp://")):
        report.add("warning", f"Remote image not downloaded (offline import): {src[:80]}")
        return None
    if src.startswith("data:image/"):
        import base64
        try:
            data = base64.b64decode(src.split(",", 1)[1], validate=False)
        except Exception:
            report.add("warning", "Invalid embedded image data")
            return None
        return sink(data, "embedded-image")
    if base is None:
        report.add("warning", f"Image not imported (no source folder): {src[:80]}")
        return None
    try:
        p = (base / src.replace("%20", " ")).resolve()
        if not p.is_relative_to(base.resolve()):
            report.add("warning", f"Image outside the document folder was not imported: {src[:80]}")
            return None
        if not p.is_file():
            report.add("warning", f"Image file not found: {src[:80]}")
            return None
        return sink(p.read_bytes(), p.name)
    except (OSError, ValueError):
        report.add("warning", f"Image could not be read: {src[:80]}")
        return None


class _Walker:
    def __init__(self, base: Path | None, sink: ImageSink, report: ImportReport):
        self.base, self.sink, self.report = base, sink, report
        self.blocks: list[Block] = []

    # -- inline ------------------------------------------------------------
    def inline_runs(self, children: list[Token]) -> tuple[list[Run], list[ImageBlock]]:
        runs: list[Run] = []
        images: list[ImageBlock] = []
        bold = italic = 0
        link: str | None = None
        for t in children:
            ty = t.type
            if ty == "text":
                runs.append(Run(t.content, bold=bool(bold), italic=bool(italic), link=link))
            elif ty == "softbreak":
                runs.append(Run(SOFT, bold=bool(bold), italic=bool(italic), link=link))
            elif ty == "hardbreak":
                runs.append(Run("\n"))
            elif ty == "code_inline":
                runs.append(Run(t.content, code=True, link=link))
            elif ty == "strong_open":
                bold += 1
            elif ty == "strong_close":
                bold -= 1
            elif ty == "em_open":
                italic += 1
            elif ty == "em_close":
                italic -= 1
            elif ty == "link_open":
                link = str(t.attrGet("href") or "") or None
            elif ty == "link_close":
                link = None
            elif ty == "image":
                src = str(t.attrGet("src") or "")
                asset = load_local_image(src, self.base, self.sink, self.report)
                if asset:
                    cap = str(t.attrGet("title") or "")
                    images.append(ImageBlock(asset=asset, alt=t.content,
                                             caption=[Run(cap)] if cap else []))
                    self.report.count("images")
                else:
                    runs.append(Run(f"[Image not imported: {t.content or src}]", italic=True))
            elif ty == "html_inline":
                self.report.add("warning", "Inline HTML kept as plain text")
                runs.append(Run(t.content))
            else:
                self.report.add("info", f"Unhandled inline element '{ty}' kept as text")
                if t.content:
                    runs.append(Run(t.content))
        return merge_runs(runs), images

    # -- blocks ------------------------------------------------------------
    def walk(self, tokens: list[Token]) -> None:
        i = 0
        n = len(tokens)
        while i < n:
            t = tokens[i]
            ty = t.type
            if ty == "heading_open":
                runs, _ = self.inline_runs(tokens[i + 1].children or [])
                self.blocks.append(HeadingBlock(level=int(t.tag[1]), runs=runs))
                i += 3
            elif ty == "paragraph_open":
                runs, images = self.inline_runs(tokens[i + 1].children or [])
                if runs and runs_text(runs).strip():
                    self.blocks.append(ParagraphBlock(runs=runs))
                self.blocks.extend(images)
                i += 3
            elif ty in ("bullet_list_open", "ordered_list_open"):
                i = self.list_block(tokens, i)
            elif ty == "blockquote_open":
                i = self.quote(tokens, i)
            elif ty in ("fence", "code_block"):
                self.blocks.append(CodeBlock(text=t.content.rstrip("\n"),
                                             language=(t.info or "").strip()))
                i += 1
            elif ty == "hr":
                self.blocks.append(SceneBreakBlock())
                i += 1
            elif ty == "table_open":
                i = self.table(tokens, i)
            elif ty == "html_block":
                self.report.add("warning", "HTML blocks were kept as plain text")
                self.blocks.append(ParagraphBlock(runs=[Run(t.content.strip())]))
                i += 1
            else:
                i += 1

    def list_block(self, tokens: list[Token], i: int) -> int:
        ordered = tokens[i].type == "ordered_list_open"
        depth = 0
        items: list[list[Run]] = []
        cur: list[Run] = []
        nested = False
        pending_images: list[ImageBlock] = []
        j = i
        while j < len(tokens):
            t = tokens[j]
            if t.type in ("bullet_list_open", "ordered_list_open"):
                depth += 1
                if depth > 1:
                    nested = True
            elif t.type in ("bullet_list_close", "ordered_list_close"):
                depth -= 1
                if depth == 0:
                    break
            elif t.type == "list_item_open":
                if cur:  # a parent item's text precedes its nested list
                    items.append(merge_runs(cur))
                cur = []
            elif t.type == "list_item_close":
                if cur:
                    items.append(merge_runs(cur))
                cur = []
            elif t.type == "inline":
                runs, imgs = self.inline_runs(t.children or [])
                if cur and depth == 1:
                    cur.append(Run(" "))
                prefix = [Run("– ")] if depth > 1 else []
                cur.extend(prefix + runs)
                pending_images.extend(imgs)
            j += 1
        if nested:
            self.report.add("info", "Nested lists were flattened to a single level")
        self.blocks.append(ListBlock(ordered=ordered, items=items))
        self.blocks.extend(pending_images)
        return j + 1

    def quote(self, tokens: list[Token], i: int) -> int:
        depth = 0
        parts: list[Run] = []
        j = i
        while j < len(tokens):
            t = tokens[j]
            if t.type == "blockquote_open":
                depth += 1
            elif t.type == "blockquote_close":
                depth -= 1
                if depth == 0:
                    break
            elif t.type == "inline":
                runs, _ = self.inline_runs(t.children or [])
                if parts:
                    parts.append(Run(" "))
                parts.extend(runs)
            j += 1
        self.blocks.append(QuoteBlock(runs=merge_runs(parts)))
        return j + 1

    def table(self, tokens: list[Token], i: int) -> int:
        rows: list[list[str]] = []
        header_rows = 0
        j = i
        in_head = False
        while j < len(tokens) and tokens[j].type != "table_close":
            t = tokens[j]
            if t.type == "thead_open":
                in_head = True
            elif t.type == "thead_close":
                in_head = False
            elif t.type == "tr_open":
                rows.append([])
                if in_head:
                    header_rows += 1
            elif t.type == "inline":
                runs, _ = self.inline_runs(t.children or [])
                rows[-1].append(runs_text(runs))
            j += 1
        self.blocks.append(TableBlock(rows=rows, header_rows=header_rows))
        return j + 1


def import_markdown(path: Path, raw: bytes, options: ImportOptions, sink: ImageSink) -> ImportResult:
    report = ImportReport(source=Path(path).name, format="Markdown")
    text = decode_text(raw, options.encoding, report)
    md = MarkdownIt("commonmark").enable("table")
    try:
        tokens = md.parse(text)
    except Exception as e:  # malformed input must never crash the application
        raise ImportFailure(f"Markdown could not be parsed: {e}") from e
    walker = _Walker(Path(path).parent, sink, report)
    walker.walk(tokens)
    title = None
    first = walker.blocks[0] if walker.blocks else None
    if options.split_level == 0 and isinstance(first, HeadingBlock) and first.level == 1:
        title = runs_text(first.runs)
    report.count("blocks", len(walker.blocks))
    mode = "always" if options.preserve_line_breaks else options.poetry_mode
    blocks = promote_chapter_headings(walker.blocks, options.split_level, options.chapter_pattern, report)
    blocks = finish_text_blocks(blocks, mode, report, False)
    sections = split_into_sections(blocks, options.split_level, stem_title(path), report)
    return ImportResult(sections, report, title)
