"""The pagination engine: places measured flows onto pages.

One implementation serves both the preview and the PDF export (they render the
LayoutResult produced here). Content is never dropped: anything that cannot be
placed validly is placed anyway and reported as a LayoutIssue.
"""
from __future__ import annotations

from typing import Callable

from ..domain.book import BookProject
from ..domain.layouts import BookSettings
from .model import (Glyphs, LayoutIssue, LayoutResult, LineItem, OutlineEntry, Page)
from .page_builder import (Atom, BuildContext, Flow, TOC_EXCLUDED, collect_toc,
                           effective_margins, outline_entries, section_flows,
                           section_signature, styles_signature)
from .typography import fonts


class LayoutCancelled(Exception):
    pass


def to_roman(n: int) -> str:
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
            (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


class Paginator:
    def __init__(self, book: BookProject):
        self.book = book
        self.settings: BookSettings = book.settings
        self.W, self.H = self.settings.page_size_pt()
        self.pages: list[Page] = []
        self.issues: list[LayoutIssue] = []
        self.block_pages: dict[str, list[int]] = {}
        self.section_pages: dict[str, int] = {}
        self.cur: Page | None = None
        self.y = 0.0
        self.pending_after = 0.0
        self.want_recto = False
        self.matter = "front"
        self.chapter_title = ""
        self.section_id: str | None = None
        self.opening_pending = False
        self._kwn_run = 0.0  # height of keep-with-next flows (e.g. a poem title) just placed on this page

    # ------------------------------------------------------------- pages
    def _geometry(self, index: int, matter: str) -> tuple[str, tuple[float, float, float, float]]:
        side = "recto" if (not self.settings.facing_pages or index % 2 == 0) else "verso"
        top, bottom, inner, outer = effective_margins(self.settings, matter)
        if self.settings.mirrored_margins and self.settings.facing_pages and side == "verso":
            x0, x1 = outer, self.W - inner
        else:
            x0, x1 = inner, self.W - outer
        return side, (x0, top, x1, self.H - bottom)

    def _append_page(self, *, blank: str | None = None, full_bleed: bool = False,
                     matter: str | None = None) -> Page:
        idx = len(self.pages)
        matter = matter or self.matter
        side, box = self._geometry(idx, matter)
        page = Page(index=idx, width=self.W, height=self.H, side=side, content_box=box,
                    matter=matter, section_id=self.section_id,
                    chapter_title=self.chapter_title, blank=blank, full_bleed=full_bleed)
        self.pages.append(page)
        return page

    def _ensure_page(self) -> Page:
        if self.cur is None:
            if self.want_recto and self.settings.facing_pages and len(self.pages) % 2 == 1:
                # padding belongs to the matter it follows, so numbering is not disturbed
                blank = self._append_page(blank="intentional", matter=self.pages[-1].matter)
                blank.used = True
            self.want_recto = False
            self.cur = self._append_page()
            self.cur.opening = self.opening_pending
            self.opening_pending = False
            self.y = self.cur.content_box[1]
            self.pending_after = 0.0
            self._kwn_run = 0.0
        return self.cur

    def _new_page(self, recto: bool = False) -> None:
        self.cur = None
        self.want_recto = self.want_recto or recto

    def _at_top(self) -> bool:
        return self.cur is None or not self.cur.used

    def _issue(self, severity: str, code: str, message: str, block_id: str | None = None) -> None:
        page = self.cur.index if self.cur else (len(self.pages) - 1 if self.pages else None)
        self.issues.append(LayoutIssue(severity, code, message, page, block_id, self.section_id))

    # ------------------------------------------------------------- control
    def _control(self, f: Flow) -> None:
        c = f.control
        if c == "section_start":
            ctl = f.ctl
            self.matter = ctl["matter"]
            self.section_id = ctl["section_id"]
            if ctl["opening"] and ctl["kind"] not in TOC_EXCLUDED:
                self.chapter_title = ctl["title"]
            if ctl["new_page"]:
                self._new_page(ctl["recto"])
                self.opening_pending = ctl["opening"]
        elif c == "page_break":
            blank = f.ctl.get("blank", False)
            recto = f.ctl.get("recto", False)
            if self.cur is not None and self.cur.used:
                self._new_page(recto)
                if blank:
                    page = self._ensure_page()
                    page.blank, page.used = "intentional", True
                    self._new_page()
            elif blank:
                page = self._ensure_page()
                page.blank, page.used = "intentional", True
                self._new_page(recto)
        elif c == "full_page":
            page = self._ensure_page()
            page.full_bleed = True
            page.used = True
            page.items.extend(f.ctl["items"])
            self._new_page()
        elif c == "blank_page":
            page = self._ensure_page()
            page.blank, page.used = "intentional", True
            self._new_page()
        elif c == "anchor":
            page = self._ensure_page()
            page.anchors[f.ctl["anchor"]] = self.y
            if f.ctl["anchor"].startswith("sec:"):
                self.section_pages.setdefault(f.ctl["anchor"][4:], page.index)

    # ------------------------------------------------------------- placing
    def _chain_height(self, flows: list[Flow], i: int, depth: int = 0, limit: float | None = None) -> float:
        f = flows[i]
        h = f.height
        if f.keep_with_next and i + 1 < len(flows) and depth < 5:
            n = flows[i + 1]
            if n.control is None and not n.own_page:
                gap = max(f.space_after, n.space_before)
                if n.keep_with_next:
                    h += gap + self._chain_height(flows, i + 1, depth + 1, limit)
                elif n.keep_together and (limit is None or n.height <= limit):
                    h += gap + n.height
                else:
                    k = min(max(n.orphan, 1), len(n.atoms))
                    h += gap + sum(a.height + (a.gap_before if j else 0.0)
                                   for j, a in enumerate(n.atoms[:k]))
        return h

    def _place_atoms(self, flow: Flow, atoms: list[Atom], start: int, page_y_offset: float = 0.0
                     ) -> None:
        page = self.cur
        assert page is not None
        x0 = page.content_box[0]
        y = self.y + page_y_offset
        for j, a in enumerate(atoms):
            if j > 0:
                y += a.gap_before
            for it in a.items:
                page.items.append(it.moved(x0, y))
            y += a.height
        self.y = y
        page.used = True
        if flow.block_id:
            lst = self.block_pages.setdefault(flow.block_id, [])
            if not lst or lst[-1] != page.index:
                lst.append(page.index)

    def add_flow(self, flows: list[Flow], i: int) -> None:
        f = flows[i]
        if f.control:
            self._control(f)
            return
        if not f.atoms:
            return
        if f.own_page:
            self._new_page()
        page = self._ensure_page()
        x0, top, x1, bottom = page.content_box
        content_h = bottom - top
        for sev, code, msg in f.issues:
            self._issue(sev, code, msg, f.block_id)

        # spacing before the flow (collapses with the previous flow's space after)
        def gap() -> float:
            return 0.0 if self._at_top_page() else max(self.pending_after, f.space_before)

        # keep-with-next / keep-together decisions need a fresh page
        if not self._at_top_page():
            remaining = bottom - self.y - gap()
            if f.keep_with_next and self._chain_height(flows, i, 0, content_h) <= content_h and \
                    self._chain_height(flows, i, 0, content_h) > remaining:
                self._new_page()
                page = self._ensure_page()
            elif f.keep_together and f.height + self._kwn_run <= content_h and f.height > remaining:
                self._new_page()
                page = self._ensure_page()

        n = len(f.atoms)
        idx = 0
        guard = 0
        while idx < n:
            guard += 1
            if guard > n + 50:  # defensive: never loop forever
                self._issue("error", "layout_loop", "Pagination did not converge", f.block_id)
                break
            page = self._ensure_page()
            x0, top, x1, bottom = page.content_box
            at_top = not page.used
            if idx == 0:
                g = f.drop if at_top else max(self.pending_after, f.space_before, f.drop)
            else:
                g = 0.0
            header = f.header_atoms if idx > 0 and f.header_atoms else []
            header_h = sum(a.height for a in header)
            y = self.y + g + header_h
            k = 0
            used_h = 0.0
            for j in range(idx, n):
                a = f.atoms[j]
                add = a.height + (a.gap_before if j > idx else 0.0)
                if y + used_h + add <= bottom + 0.01:
                    used_h += add
                    k += 1
                else:
                    break
            fit_k = k
            remaining_atoms = n - idx - k
            if remaining_atoms > 0:  # a page break falls inside this flow
                if f.keep_together and idx == 0 and not at_top and f.height + self._kwn_run <= content_h:
                    k = 0
                else:
                    orphans = min(f.orphan, n)
                    if idx == 0 and k < orphans:
                        k = 0
                    widows = min(f.widow, n)
                    if k and (n - idx - k) < widows:
                        k = max(n - idx - widows, 0)
                        if idx == 0 and k < orphans:
                            k = 0
            if k == 0:
                if at_top:
                    if fit_k > 0:
                        k = fit_k  # rules cannot be honoured on an empty page; use what fits
                    else:
                        # nothing fits on an empty page: place it anyway and report it
                        k = 1
                        self._issue("error", "overflow",
                                    "Content is taller than the available page area and "
                                    "will be clipped", f.block_id)
                else:
                    self._new_page()
                    continue
            if idx == 0:
                for anc in f.anchors:
                    page.anchors[anc] = self.y + g
                    if anc.startswith("sec:"):
                        self.section_pages.setdefault(anc[4:], page.index)
            offset = g
            if f.own_page and idx == 0 and k == n:
                offset = max((bottom - self.y - f.height) / 2, 0.0)
            if header:
                self._place_atoms(f, header, 0, offset)
                offset = 0.0
            self._place_atoms(f, f.atoms[idx: idx + k], idx, offset)
            idx += k
            if idx < n:
                if f.ctl.get("poem"):
                    self._issue("info", "poem_continues",
                                "A poem continues on the next page", f.block_id)
                self._new_page()
        self.pending_after = f.space_after
        self._kwn_run = self._kwn_run + f.height + f.space_after if f.keep_with_next else 0.0
        if f.own_page:
            self._new_page()

    def _at_top_page(self) -> bool:
        return self.cur is None or not self.cur.used

    def finish(self) -> None:
        if not self.pages:
            self._append_page(blank="intentional").used = True
            self.issues.append(LayoutIssue("info", "empty_book", "The book has no content", 0))


# ----------------------------------------------------------------- decoration
def assign_page_labels(pages: list[Page], settings: BookSettings) -> None:
    front_n = 0
    arabic_n = 0
    started_main = False
    mode = settings.front_numbering
    seen_content = False
    for p in pages:
        if p.full_bleed:
            p.label = ""
            continue
        if p.blank and not seen_content:
            p.label = ""  # blank leaves before the first real page are not counted
            continue
        seen_content = True
        if p.matter == "front":
            front_n += 1
            if mode == "roman":
                label = to_roman(front_n)
            elif mode == "arabic":
                arabic_n += 1
                label = str(arabic_n)
            else:
                label = ""
        else:
            if not started_main and mode != "arabic":
                arabic_n = 0
            started_main = True
            arabic_n += 1
            label = str(arabic_n)
        p.label = "" if p.blank else label


def decorate_pages(pages: list[Page], book: BookProject) -> None:
    s = book.settings
    md = book.metadata
    from ..domain.styles import StyleSet
    style = StyleSet(book.styles).resolve("header_footer")
    fam = style.font_family
    for p in pages:
        p.decorations.clear()
        if p.full_bleed or p.blank:
            continue
        x0, top, x1, bottom = p.content_box
        face = fonts.face(fam, style.bold, style.italic)

        def put(text: str, y: float, align: str) -> None:
            w = fonts.width(text, face.key, style.font_size)
            if align == "left":
                x = x0
            elif align == "right":
                x = x1 - w
            else:
                x = (x0 + x1) / 2 - w / 2
            p.decorations.append(Glyphs(x=x, y=y, text=text, font=face.key, size=style.font_size,
                                        color=style.color, width=w, kind="header"))

        def fmt(t: str) -> str:
            return (t.replace("{title}", md.title).replace("{author}", md.author)
                    .replace("{chapter}", p.chapter_title).replace("{page}", p.label)).strip()

        if p.matter != "front" and not p.opening:
            tpl = s.header_recto if p.side == "recto" else s.header_verso
            text = fmt(tpl)
            if text:
                y = top * 0.55
                align = "center"
                if s.facing_pages:
                    align = "right" if p.side == "recto" else "left"
                put(text, y, align)
                if s.header_rule:
                    p.decorations.append(LineItem(x0, y + 5, x1, y + 5, 0.4, "#888888"))
        if s.footer_position != "none" and p.label:
            text = fmt(s.footer)
            if text:
                y = p.height - (p.height - bottom) * 0.45
                align = "center"
                if s.footer_position == "outer":
                    align = "right" if p.side == "recto" else "left"
                put(text, y, align)


class LayoutEngine:
    """Builds LayoutResults. Keeps a flow cache so edits re-measure only what changed."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, int], list[Flow]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def _flows(self, book: BookProject, labels: dict[str, str],
               cancel: Callable[[], bool] | None) -> list[Flow]:
        ctx = BuildContext(book)
        sig = styles_signature(book)
        flows: list[Flow] = []

        def rec(sections, depth):
            for s in sections:
                if cancel and cancel():
                    raise LayoutCancelled()
                if not s.enabled:
                    continue
                if s.kind == "toc":
                    flows.extend(section_flows(book, ctx, s, depth, labels))
                    continue
                key = (sig, section_signature(book, s), depth)
                cached = self._cache.get(key)
                if cached is None:
                    cached = section_flows(book, ctx, s, depth, labels)
                    if len(self._cache) > 3000:
                        self._cache.clear()
                    self._cache[key] = cached
                flows.extend(cached)

        # section_flows recurses into children, so only iterate top-level sections.
        rec(book.sections, 1)
        return flows

    def build(self, book: BookProject, cancel: Callable[[], bool] | None = None) -> LayoutResult:
        labels: dict[str, str] = {}
        has_toc = any(s.kind == "toc" and s.enabled for s in book.walk())
        result: LayoutResult | None = None
        for _ in range(4 if has_toc else 1):
            pag = Paginator(book)
            flows = self._flows(book, labels, cancel)
            for i in range(len(flows)):
                if cancel and i % 200 == 0 and cancel():
                    raise LayoutCancelled()
                pag.add_flow(flows, i)
            pag.finish()
            assign_page_labels(pag.pages, book.settings)
            decorate_pages(pag.pages, book)
            result = self._result(book, pag)
            new_labels = {}
            for e in collect_toc(book):
                pg = next((p for p in pag.pages if e.anchor in p.anchors), None)
                if pg is not None:
                    new_labels[e.anchor] = pg.label or str(pg.index + 1)
            if new_labels == labels or not has_toc:
                break
            labels = new_labels
        assert result is not None
        return result

    def _result(self, book: BookProject, pag: Paginator) -> LayoutResult:
        issues = list(pag.issues)
        for p in pag.pages:
            if not p.items and p.blank is None and not p.full_bleed:
                issues.append(LayoutIssue("warning", "accidental_blank_page",
                                          f"Page {p.index + 1} is blank but not marked intentional",
                                          p.index, None, p.section_id))
        outline: list[OutlineEntry] = []
        for e in outline_entries(book):
            pg = next((p for p in pag.pages if e.anchor in p.anchors), None)
            if pg is not None:
                outline.append(OutlineEntry(e.level, e.title, e.anchor, pg.index))
        w, h = book.settings.page_size_pt()
        return LayoutResult(pages=pag.pages, issues=issues, outline=outline, page_width=w,
                            page_height=h, block_pages=pag.block_pages,
                            section_pages=pag.section_pages)


def build_layout(book: BookProject) -> LayoutResult:
    return LayoutEngine().build(book)
