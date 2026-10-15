"""HTML import with the standard-library parser. Scripts are never executed."""
from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from ..domain.content_blocks import (Block, CodeBlock, HeadingBlock, ImageBlock, ListBlock,
                                     ParagraphBlock, QuoteBlock, Run, SceneBreakBlock,
                                     TableBlock, merge_runs, runs_text)
from .base import (ImageSink, ImportOptions, ImportReport, ImportResult, split_into_sections,
                   stem_title)
from .markdown_importer import load_local_image
from .txt_importer import decode_text

SKIP_TAGS = {"script", "style", "noscript", "iframe", "object", "embed", "template"}
BLOCK_TAGS = {"p", "div", "li", "td", "th", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5",
              "h6", "ul", "ol", "table", "tr", "section", "article", "figure", "figcaption",
              "body", "hr"}


class _Parser(HTMLParser):
    def __init__(self, base: Path | None, sink: ImageSink, report: ImportReport):
        super().__init__(convert_charrefs=True)
        self.base, self.sink, self.report = base, sink, report
        self.blocks: list[Block] = []
        self.runs: list[Run] = []
        self.skip = 0
        self.bold = self.italic = self.code = 0
        self.link: str | None = None
        self.heading = 0
        self.in_pre = False
        self.in_quote = 0
        self.list_stack: list[list] = []  # [ordered, items]
        self.item_runs: list[Run] | None = None
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.header_cells = 0
        self.title: str | None = None
        self.in_title = False

    def _flush_paragraph(self) -> None:
        runs = merge_runs(self.runs)
        self.runs = []
        if not runs or not runs_text(runs).strip():
            return
        if self.heading:
            self.blocks.append(HeadingBlock(level=self.heading, runs=runs))
        elif self.in_quote:
            self.blocks.append(QuoteBlock(runs=runs))
        else:
            self.blocks.append(ParagraphBlock(runs=runs))

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip += 1
            self.report.add("warning", f"<{tag}> content was ignored (not executed or imported)")
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_paragraph()
            self.heading = int(tag[1])
        elif tag in ("p", "div", "section", "article", "figure", "figcaption"):
            if self.item_runs is None:
                self._flush_paragraph()
        elif tag == "br":
            if self.cell is not None:
                self.cell.append("\n")
            else:
                self.runs.append(Run("\n"))
        elif tag in ("b", "strong"):
            self.bold += 1
        elif tag in ("i", "em", "cite"):
            self.italic += 1
        elif tag == "code" and not self.in_pre:
            self.code += 1
        elif tag == "a":
            self.link = a.get("href") or None
        elif tag == "blockquote":
            self._flush_paragraph()
            self.in_quote += 1
        elif tag == "pre":
            self._flush_paragraph()
            self.in_pre = True
            self.pre_text: list[str] = []
        elif tag in ("ul", "ol"):
            self._flush_paragraph()
            self.list_stack.append([tag == "ol", []])
        elif tag == "li":
            self.item_runs = []
        elif tag == "hr":
            self._flush_paragraph()
            self.blocks.append(SceneBreakBlock())
        elif tag == "img":
            self._flush_paragraph()
            src = a.get("src") or ""
            asset = load_local_image(src, self.base, self.sink, self.report)
            if asset:
                self.blocks.append(ImageBlock(asset=asset, alt=a.get("alt", ""),
                                              caption=[Run(a["title"])] if a.get("title") else []))
                self.report.count("images")
            else:
                self.runs.append(Run(f"[Image not imported: {a.get('alt') or src[:60]}]", italic=True))
        elif tag == "table":
            self._flush_paragraph()
            self.table = []
            self.header_cells = 0
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            if tag == "th" and len(self.table or []) == 0:
                self.header_cells += 1
        elif tag in ("video", "audio", "svg", "canvas", "form", "input"):
            self.report.add("warning", f"<{tag}> elements are not supported and were skipped")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(self.skip - 1, 0)
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_paragraph()
            self.heading = 0
        elif tag in ("p", "div", "section", "article", "figure", "figcaption"):
            if self.item_runs is None:
                self._flush_paragraph()
        elif tag in ("b", "strong"):
            self.bold = max(self.bold - 1, 0)
        elif tag in ("i", "em", "cite"):
            self.italic = max(self.italic - 1, 0)
        elif tag == "code" and not self.in_pre:
            self.code = max(self.code - 1, 0)
        elif tag == "a":
            self.link = None
        elif tag == "blockquote":
            self._flush_paragraph()
            self.in_quote = max(self.in_quote - 1, 0)
        elif tag == "pre":
            self.blocks.append(CodeBlock(text="".join(self.pre_text).strip("\n")))
            self.in_pre = False
        elif tag == "li" and self.item_runs is not None:
            if self.list_stack and runs_text(self.item_runs).strip():
                self.list_stack[-1][1].append(merge_runs(self.item_runs))
            self.item_runs = None
        elif tag in ("ul", "ol") and self.list_stack:
            ordered, items = self.list_stack.pop()
            if items:
                self.blocks.append(ListBlock(ordered=ordered, items=items))
        elif tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.blocks.append(TableBlock(rows=self.table,
                                              header_rows=1 if self.header_cells else 0))
            self.table = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.in_title:
            self.title = (self.title or "") + data
            return
        if self.in_pre:
            self.pre_text.append(data)
            return
        if self.cell is not None:
            self.cell.append(data)
            return
        text = " ".join(data.split()) if data.strip() else (" " if data else "")
        if not text:
            return
        if data[:1].isspace() and not text.startswith(" "):
            text = " " + text
        if data[-1:].isspace() and not text.endswith(" "):
            text += " "
        run = Run(text, bold=bool(self.bold), italic=bool(self.italic), code=bool(self.code),
                  link=self.link)
        if self.item_runs is not None:
            self.item_runs.append(run)
        else:
            self.runs.append(run)


def import_html(path: Path, raw: bytes, options: ImportOptions, sink: ImageSink) -> ImportResult:
    report = ImportReport(source=Path(path).name, format="HTML")
    text = decode_text(raw, options.encoding, report)
    p = _Parser(Path(path).parent, sink, report)
    try:
        p.feed(text)
        p.close()
    except Exception as e:
        report.add("error", f"HTML was malformed and may be incomplete: {e}")
    p._flush_paragraph()
    for b in p.blocks:  # trim whitespace at run edges of paragraphs
        if isinstance(b, (ParagraphBlock, HeadingBlock, QuoteBlock)) and b.runs:
            b.runs[0].text = b.runs[0].text.lstrip()
            b.runs[-1].text = b.runs[-1].text.rstrip()
    report.count("blocks", len(p.blocks))
    sections = split_into_sections(p.blocks, options.split_level,
                                   (p.title or "").strip() or stem_title(path), report)
    return ImportResult(sections, report, (p.title or "").strip() or None)
