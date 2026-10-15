"""Properties panel: Section, Block, Book (page, typography, metadata) and Styles tabs."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout,
                               QWidget)

from ..application_state import AppState
from ..domain.layouts import PAGE_SIZES
from ..domain.sections import ALL_KINDS, KIND_LABELS
from ..domain.styles import StyleDefinition, StyleSet, default_styles
from ..layout.typography import LOGICAL_FAMILIES, fonts
from ..services.template_service import apply_template

STYLE_LABELS = {
    "body": "Body Text", "first_paragraph": "First Paragraph", "book_title": "Book Title",
    "subtitle": "Subtitle", "author": "Author", "part_title": "Part Title",
    "chapter_title": "Chapter Title", "heading1": "Section Heading (H1)", "heading2": "Heading 2",
    "heading3": "Heading 3", "heading4": "Heading 4", "block_quote": "Block Quote",
    "caption": "Caption", "footnote": "Footnote", "code": "Code", "poetry": "Poetry",
    "poetry_title": "Poem Title", "recipe_heading": "Recipe Heading", "table": "Table Text",
    "table_header": "Table Header", "bibliography_entry": "Bibliography Entry",
    "toc_entry": "Contents Entry", "toc_title": "Contents Title", "scene_break": "Scene Break",
    "header_footer": "Header / Footer", "callout": "Callout (note, exercise)",
}
BODY_CONTROLLED = {"font_family", "font_size", "line_height", "space_after", "align", "first_indent"}


def _scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QScrollArea.NoFrame)
    sa.setWidget(widget)
    return sa


def _family_items() -> list[str]:
    return list(LOGICAL_FAMILIES) + fonts.installed_families()


class SectionTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.section_id: str | None = None
        self._loading = False
        form = QFormLayout(self)
        self.title = QLineEdit()
        self.title.setAccessibleName("Section title")
        self.kind = QComboBox()
        for k in ALL_KINDS:
            self.kind.addItem(KIND_LABELS[k], k)
        self.enabled = QCheckBox("Include in the book")
        self.in_toc = QCheckBox("Show in table of contents")
        self.show_title = QCheckBox("Print the title on the page")
        self.new_page = QComboBox()
        self.new_page.addItem("Follow book setting", None)
        self.new_page.addItem("Always start on a new page", True)
        self.new_page.addItem("Continue on the current page", False)
        self.stats = QLabel("")
        self.stats.setProperty("muted", True)
        form.addRow("Title", self.title)
        form.addRow("Type", self.kind)
        form.addRow("", self.enabled)
        form.addRow("", self.in_toc)
        form.addRow("", self.show_title)
        form.addRow("Page break", self.new_page)
        form.addRow("", self.stats)
        self.title.editingFinished.connect(self._title_done)
        self.kind.activated.connect(lambda _: self._apply(kind=self.kind.currentData()))
        self.enabled.toggled.connect(lambda v: self._apply(enabled=v))
        self.in_toc.toggled.connect(lambda v: self._apply(in_toc=v))
        self.show_title.toggled.connect(lambda v: self._apply(show_title=v))
        self.new_page.activated.connect(lambda _: self._apply(new_page=self.new_page.currentData()))

    def load(self, section_id: str | None) -> None:
        self.section_id = section_id
        sec = self.state.project.find_section(section_id) if section_id else None
        self._loading = True
        self.setEnabled(sec is not None)
        if sec:
            self.title.setText(sec.title)
            self.kind.setCurrentIndex(max(ALL_KINDS.index(sec.kind), 0) if sec.kind in ALL_KINDS else 0)
            self.enabled.setChecked(sec.enabled)
            self.in_toc.setChecked(sec.in_toc)
            self.show_title.setChecked(sec.show_title)
            self.new_page.setCurrentIndex({None: 0, True: 1, False: 2}[sec.new_page])
            self.stats.setText(f"{self.state.project.word_count(sec):,} words • "
                               f"{self.state.project.char_count(sec):,} characters")
        self._loading = False

    def _title_done(self) -> None:
        if self._loading or not self.section_id:
            return
        sec = self.state.project.find_section(self.section_id)
        if sec and sec.title != self.title.text():
            self.state.rename_section(self.section_id, self.title.text())

    def _apply(self, **attrs) -> None:
        if self._loading or not self.section_id:
            return
        self.state.set_section_attr(self.section_id, **attrs)


class BlockTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.editor = None
        self._loading = False
        form = QFormLayout(self)
        self.kind = QLabel("—")
        self.level = QSpinBox(minimum=1, maximum=4)
        self.level.setToolTip("Heading level")
        self.keep = QCheckBox("Keep with next block")
        self.keep.setToolTip("Never leave this block alone at the bottom of a page")
        self.style = QComboBox()
        self.style.addItem("Automatic", "")
        for name, label in STYLE_LABELS.items():
            self.style.addItem(label, name)
        self.locked = QCheckBox("Locked (protect from edits and replace-all)")
        form.addRow("Block type", self.kind)
        form.addRow("Heading level", self.level)
        form.addRow("", self.keep)
        form.addRow("Named style", self.style)
        form.addRow("", self.locked)
        hint = QLabel("Select text in the editor to see its block here.")
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        self.model_box = QGroupBox("This block")
        mf = QFormLayout(self.model_box)
        self.poem_title = QLineEdit()
        self.poem_title.setPlaceholderText("Poem title (optional)")
        self.one_page = QCheckBox("One poem per page")
        self.cont = QCheckBox("Print “(continued)” when it runs onto another page")
        self.h_toc = QCheckBox("Show this heading in the table of contents")
        self.pb_blank = QCheckBox("Insert a blank page")
        self.pb_recto = QCheckBox("Continue on the next right-hand page")
        for w in (self.poem_title, self.one_page, self.cont, self.h_toc, self.pb_blank, self.pb_recto):
            mf.addRow(w)
        form.addRow(self.model_box)
        form.addRow(hint)
        self.poem_title.editingFinished.connect(lambda: self._model(title=self.poem_title.text().strip()))
        self.one_page.toggled.connect(lambda v: self._model(one_per_page=v))
        self.cont.toggled.connect(lambda v: self._model(continuation_marker=v))
        self.h_toc.toggled.connect(lambda v: self._model(in_toc=v))
        self.pb_blank.toggled.connect(lambda v: self._model(blank=v))
        self.pb_recto.toggled.connect(lambda v: self._model(recto=v))
        self.level.valueChanged.connect(lambda v: self._set(level=v))
        self.keep.toggled.connect(lambda v: self._set(keep_with_next=v))
        self.style.activated.connect(lambda _: self._set(style=self.style.currentData()))
        self.locked.toggled.connect(self._lock)

    def bind(self, editor) -> None:
        self.editor = editor
        editor.block_context_changed.connect(self.refresh)

    def refresh(self) -> None:
        if self.editor is None:
            return
        info = self.editor.block_properties()
        self._loading = True
        names = {"paragraph": "Paragraph", "heading": "Heading", "quote": "Quote", "code": "Code block",
                 "poetry": "Poetry", "poem_title": "Poem title", "list_bullet": "Bullet list",
                 "list_number": "Numbered list", "scene": "Scene break", "placeholder": "Image / table / break",
                 "exercise": "Textbook element", "footnote": "Footnote", "quote_attr": "Attribution"}
        self.kind.setText(names.get(info["kind"], info["kind"]))
        self.level.setEnabled(info["kind"] == "heading")
        self.level.setValue(info["level"] if info["kind"] == "heading" else 1)
        self.keep.setChecked(info["keep_with_next"])
        idx = self.style.findData(info["style"])
        self.style.setCurrentIndex(max(idx, 0))
        self.locked.setChecked(info["locked"])
        from ..domain.content_blocks import HeadingBlock, PageBreakBlock, PoetryBlock
        mb = self.editor.current_model_block() if info["id"] else None
        for w in (self.poem_title, self.one_page, self.cont):
            w.setVisible(isinstance(mb, PoetryBlock))
        self.h_toc.setVisible(isinstance(mb, HeadingBlock))
        for w in (self.pb_blank, self.pb_recto):
            w.setVisible(isinstance(mb, PageBreakBlock))
        self.model_box.setVisible(isinstance(mb, (PoetryBlock, HeadingBlock, PageBreakBlock)))
        if isinstance(mb, PoetryBlock):
            self.poem_title.setText(mb.title)
            self.one_page.setChecked(mb.one_per_page)
            self.cont.setChecked(mb.continuation_marker)
        elif isinstance(mb, HeadingBlock):
            self.h_toc.setChecked(mb.in_toc)
        elif isinstance(mb, PageBreakBlock):
            self.pb_blank.setChecked(mb.blank)
            self.pb_recto.setChecked(mb.recto)
        self._loading = False

    def _set(self, **props) -> None:
        if not self._loading and self.editor:
            self.editor.set_block_property(**props)

    def _model(self, **props) -> None:
        if not self._loading and self.editor:
            self.editor.set_model_property(**props)

    def _lock(self, v: bool) -> None:
        if not self._loading and self.editor:
            self.editor.set_locked(v)


class BookTab(QWidget):
    templates_requested = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._loading = False
        outer = QVBoxLayout()
        outer.setSpacing(10)
        self._widgets: dict[str, tuple[QWidget, Callable[[], Any]]] = {}
        meta = QGroupBox("Book")
        mf = QFormLayout(meta)
        for key, label in (("title", "Title"), ("subtitle", "Subtitle"), ("author", "Author"),
                           ("language", "Language"), ("publisher", "Publisher"), ("isbn", "ISBN"),
                           ("year", "Year"), ("rights", "Rights statement")):
            le = QLineEdit()
            le.setAccessibleName(label)
            le.editingFinished.connect(lambda k=key, w=le: self._meta(k, w.text()))
            mf.addRow(label, le)
            self._widgets["meta." + key] = (le, le.text)
        outer.addWidget(meta)

        tpl = QGroupBox("Template")
        tl = QHBoxLayout(tpl)
        self.template = QComboBox()
        self.template.setToolTip("Applying a template changes page setup and styles, "
                                 "except styles you customised")
        apply_btn = QPushButton("Apply")
        apply_btn.setToolTip("Apply the chosen template to this book")
        manage = QPushButton("Library…")
        manage.setToolTip("Preview, duplicate, import, export and reset templates")
        tl.addWidget(self.template, 1)
        tl.addWidget(apply_btn)
        tl.addWidget(manage)
        apply_btn.clicked.connect(self.apply_template)
        manage.clicked.connect(self.templates_requested)
        outer.addWidget(tpl)

        page = QGroupBox("Page")
        pf = QFormLayout(page)
        self.size = QComboBox()
        self.size.addItems(list(PAGE_SIZES))
        self.size.activated.connect(lambda _: self._page_size())
        self.w = self._dspin(pf, "Width (mm)", "width_mm", 40, 600, 1)
        self.h = self._dspin(pf, "Height (mm)", "height_mm", 40, 800, 1)
        pf.insertRow(0, "Size", self.size)
        self.landscape = self._check(pf, "Landscape", "landscape")
        self.facing = self._check(pf, "Facing pages (left/right)", "facing_pages")
        self.mirror = self._check(pf, "Mirrored inner/outer margins", "mirrored_margins")
        self.m_top = self._dspin(pf, "Top margin (mm)", "margins.top", 5, 100, 1)
        self.m_bot = self._dspin(pf, "Bottom margin (mm)", "margins.bottom", 5, 100, 1)
        self.m_in = self._dspin(pf, "Inner margin (mm)", "margins.inner", 5, 100, 1)
        self.m_out = self._dspin(pf, "Outer margin (mm)", "margins.outer", 5, 100, 1)
        self.gutter = self._dspin(pf, "Gutter (mm)", "gutter_mm", 0, 30, 0.5)
        self.bleed = self._dspin(pf, "Print bleed (mm)", "bleed_mm", 0, 10, 0.5)
        outer.addWidget(page)

        typo = QGroupBox("Typography")
        tf = QFormLayout(typo)
        self.font = QComboBox()
        self.font.setEditable(True)
        self.font.addItems(_family_items())
        self.font.setToolTip("Body font. A warning appears if it lacks glyphs your text uses.")
        self.font.activated.connect(lambda _: self._set("body_font", self.font.currentText()))
        tf.addRow("Body font", self.font)
        self._dspin(tf, "Size (pt)", "body_size", 6, 36, 0.5)
        self._dspin(tf, "Line spacing (×)", "line_height", 1.0, 3.0, 0.05)
        self._dspin(tf, "Paragraph spacing (pt)", "paragraph_spacing", 0, 40, 1)
        self._dspin(tf, "First-line indent (pt)", "first_line_indent", 0, 60, 1)
        self._check(tf, "Justify text", "justify")
        self._ispin(tf, "Widow lines", "widow_lines", 1, 4)
        self._ispin(tf, "Orphan lines", "orphan_lines", 1, 4)
        outer.addWidget(typo)

        ch = QGroupBox("Chapters, contents and numbering")
        cf = QFormLayout(ch)
        self._check(cf, "Chapters start on a new page", "chapter_new_page")
        self._check(cf, "Chapters start on right-hand pages", "chapter_right_page")
        self._check(cf, "Table of contents", "show_toc")
        self._ispin(cf, "Contents depth", "toc_depth", 1, 5)
        self._check(cf, "Contents page numbers", "toc_page_numbers")
        fn = QComboBox()
        fn.addItems(["roman", "arabic", "none"])
        fn.activated.connect(lambda _: self._set("front_numbering", fn.currentText()))
        cf.addRow("Front matter numbers", fn)
        self._widgets["front_numbering"] = (fn, fn.currentText)
        self._text(cf, "Header (left pages)", "header_verso")
        self._text(cf, "Header (right pages)", "header_recto")
        self._text(cf, "Footer", "footer")
        fp = QComboBox()
        fp.addItems(["center", "outer", "none"])
        fp.activated.connect(lambda _: self._set("footer_position", fp.currentText()))
        cf.addRow("Footer position", fp)
        self._widgets["footer_position"] = (fp, fp.currentText)
        self._check(cf, "Rule under header", "header_rule")
        tokens = QLabel("Tokens: {title} {author} {chapter} {page}")
        tokens.setProperty("muted", True)
        cf.addRow(tokens)
        outer.addWidget(ch)
        outer.addStretch(1)
        host = QWidget()
        host.setLayout(outer)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_scroll(host))
        state.project_changed.connect(self.load)
        state.settings_changed.connect(self.load)
        self.load()

    # -- widget factories ------------------------------------------------------
    def _get(self, path: str) -> Any:
        obj: Any = self.state.project.settings
        for part in path.split("."):
            obj = getattr(obj, part)
        return obj

    def _set(self, path: str, value: Any) -> None:
        if self._loading:
            return

        def fn(p) -> None:
            obj: Any = p.settings
            parts = path.split(".")
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
            if path in ("width_mm", "height_mm"):
                p.settings.page_size = "Custom"
        self.state.edit(f"Change {path}", fn, kind="settings", merge_key=f"set:{path}")

    def _dspin(self, form: QFormLayout, label: str, path: str, lo: float, hi: float, step: float):
        sp = QDoubleSpinBox(minimum=lo, maximum=hi, singleStep=step, decimals=2 if step < 1 else 1)
        sp.setAccessibleName(label)
        sp.valueChanged.connect(lambda v, p=path: self._set(p, round(v, 3)))
        form.addRow(label, sp)
        self._widgets[path] = (sp, sp.value)
        return sp

    def _ispin(self, form: QFormLayout, label: str, path: str, lo: int, hi: int):
        sp = QSpinBox(minimum=lo, maximum=hi)
        sp.setAccessibleName(label)
        sp.valueChanged.connect(lambda v, p=path: self._set(p, v))
        form.addRow(label, sp)
        self._widgets[path] = (sp, sp.value)
        return sp

    def _check(self, form: QFormLayout, label: str, path: str):
        cb = QCheckBox(label)
        cb.toggled.connect(lambda v, p=path: self._set(p, v))
        form.addRow("", cb)
        self._widgets[path] = (cb, cb.isChecked)
        return cb

    def _text(self, form: QFormLayout, label: str, path: str):
        le = QLineEdit()
        le.setAccessibleName(label)
        le.editingFinished.connect(lambda p=path, w=le: self._set(p, w.text()))
        form.addRow(label, le)
        self._widgets[path] = (le, le.text)
        return le

    def _page_size(self) -> None:
        name = self.size.currentText()

        def fn(p) -> None:
            p.settings.set_page_size(name)
        self.state.edit("Change page size", fn, kind="settings")

    def _meta(self, key: str, value: str) -> None:
        if self._loading or getattr(self.state.project.metadata, key) == value:
            return
        self.state.edit("Change book details", lambda p: setattr(p.metadata, key, value),
                        kind="settings", merge_key=f"meta:{key}")

    # -- load ------------------------------------------------------------------
    def load(self) -> None:
        self._loading = True
        p = self.state.project
        st = p.settings
        for key, (w, _) in self._widgets.items():
            if key.startswith("meta."):
                w.setText(getattr(p.metadata, key[5:]))
                continue
            val = self._get(key)
            if isinstance(w, QDoubleSpinBox):
                w.setValue(float(val))
            elif isinstance(w, QSpinBox):
                w.setValue(int(val))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(val))
            elif isinstance(w, QLineEdit):
                w.setText(str(val))
            elif isinstance(w, QComboBox):
                w.setCurrentText(str(val))
        self.size.setCurrentText(st.page_size if st.page_size in PAGE_SIZES else "Custom")
        custom = st.page_size == "Custom"
        self.w.setEnabled(custom)
        self.h.setEnabled(custom)
        self.font.setCurrentText(st.body_font)
        self.template.blockSignals(True)
        self.template.clear()
        for t in self.state.templates.list_templates():
            self.template.addItem(t["name"], t["key"])
        i = self.template.findData(st.template)
        self.template.setCurrentIndex(max(i, 0))
        self.template.blockSignals(False)
        self._loading = False

    def apply_template(self) -> None:
        key = self.template.currentData()
        if not key:
            return
        tpl = self.state.templates.get(key)
        kept = [n for n in tpl.get("styles", {}) if self.state.project.styles.get(n)
                and self.state.project.styles[n].user_modified]
        msg = (f"Apply the template '{tpl['name']}'?\n\nThis changes page size, margins, typography "
               "and styles. You can undo it with Ctrl+Z.")
        if kept:
            msg += "\n\nYour customised styles will be kept: " + ", ".join(STYLE_LABELS.get(k, k) for k in kept)
        if QMessageBox.question(self, "Apply template", msg) != QMessageBox.Yes:
            return
        self.state.edit("Apply template", lambda p: apply_template(p, tpl), kind="settings")


class StylesTab(QWidget):
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self._loading = False
        self.name = QComboBox()
        self.name.setAccessibleName("Style")
        form = QFormLayout()
        self.family = QComboBox()
        self.family.setEditable(True)
        self.family.addItems(_family_items())
        self.size = QDoubleSpinBox(minimum=5, maximum=96, singleStep=0.5)
        self.bold = QCheckBox("Bold")
        self.italic = QCheckBox("Italic")
        self.color = QPushButton("#000000")
        self.before = QDoubleSpinBox(minimum=0, maximum=300, singleStep=1)
        self.after = QDoubleSpinBox(minimum=0, maximum=300, singleStep=1)
        self.leading = QDoubleSpinBox(minimum=0.8, maximum=3, singleStep=0.05, decimals=2)
        self.align = QComboBox()
        self.align.addItems(["left", "center", "right", "justify"])
        self.first = QDoubleSpinBox(minimum=-60, maximum=120, singleStep=1)
        self.left = QDoubleSpinBox(minimum=0, maximum=200, singleStep=1)
        self.keep = QCheckBox("Keep with next")
        self.pbb = QCheckBox("Start on a new page")
        self.rows = {
            "font_family": ("Font", self.family), "font_size": ("Size (pt)", self.size),
            "color": ("Color", self.color), "space_before": ("Space before (pt)", self.before),
            "space_after": ("Space after (pt)", self.after), "line_height": ("Line spacing (×)", self.leading),
            "align": ("Alignment", self.align), "first_indent": ("First-line indent (pt)", self.first),
            "left_indent": ("Left indent (pt)", self.left)}
        for key, (label, w) in self.rows.items():
            form.addRow(label, w)
        form.addRow("", self.bold)
        form.addRow("", self.italic)
        form.addRow("", self.keep)
        form.addRow("", self.pbb)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("muted", True)
        self.reset = QPushButton("Reset style to template default")
        self.reset.setToolTip("Discard your changes to this style")
        lay = QVBoxLayout(self)
        lay.addWidget(self.name)
        lay.addLayout(form)
        lay.addWidget(self.note)
        lay.addWidget(self.reset)
        lay.addStretch(1)

        self.name.activated.connect(lambda _: self.load_style())
        self.family.activated.connect(lambda _: self._set("font_family", self.family.currentText()))
        self.family.lineEdit().editingFinished.connect(lambda: self._set("font_family", self.family.currentText()))
        for sp, key in ((self.size, "font_size"), (self.before, "space_before"), (self.after, "space_after"),
                        (self.leading, "line_height"), (self.first, "first_indent"), (self.left, "left_indent")):
            sp.valueChanged.connect(lambda v, k=key: self._set(k, round(v, 3)))
        self.align.activated.connect(lambda _: self._set("align", self.align.currentText()))
        self.bold.toggled.connect(lambda v: self._set("bold", v))
        self.italic.toggled.connect(lambda v: self._set("italic", v))
        self.keep.toggled.connect(lambda v: self._set("keep_with_next", v))
        self.pbb.toggled.connect(lambda v: self._set("page_break_before", v))
        self.color.clicked.connect(self._pick_color)
        self.reset.clicked.connect(self._reset)
        state.project_changed.connect(self.refresh_names)
        state.settings_changed.connect(self.refresh_names)
        self.refresh_names()

    def refresh_names(self) -> None:
        cur = self.name.currentData()
        self.name.blockSignals(True)
        self.name.clear()
        for key in STYLE_LABELS:
            if key in self.state.project.styles:
                self.name.addItem(STYLE_LABELS[key] + ("  ●" if self.state.project.styles[key].user_modified else ""), key)
        i = self.name.findData(cur)
        self.name.setCurrentIndex(max(i, 0))
        self.name.blockSignals(False)
        self.load_style()

    def _resolved(self, name: str):
        from ..layout.page_builder import BuildContext
        return BuildContext(self.state.project).style(name)

    def load_style(self) -> None:
        name = self.name.currentData()
        if not name or name not in self.state.project.styles:
            return
        self._loading = True
        r = self._resolved(name)
        self.family.setCurrentText(r.font_family)
        self.size.setValue(r.font_size)
        self.bold.setChecked(r.bold)
        self.italic.setChecked(r.italic)
        self.color.setText(r.color)
        self.color.setStyleSheet(f"background: {r.color}; color: {'#000' if QColor(r.color).lightness() > 128 else '#fff'};")
        self.before.setValue(r.space_before)
        self.after.setValue(r.space_after)
        self.leading.setValue(r.line_height)
        self.align.setCurrentText(r.align)
        self.first.setValue(r.first_indent)
        self.left.setValue(r.left_indent)
        self.keep.setChecked(r.keep_with_next)
        self.pbb.setChecked(r.page_break_before)
        controlled = name == "body"
        for key in BODY_CONTROLLED:
            w = self.rows.get(key, (None, None))[1]
            if w is not None:
                w.setEnabled(not controlled)
        self.note.setText("Body Text follows the Typography settings in the Book tab. "
                          "All other styles inherit from it." if controlled else
                          ("Customised ● — kept when a template is applied."
                           if self.state.project.styles[name].user_modified else
                           "Inherits from: " + (self.state.project.styles[name].based_on or "—")))
        self._loading = False

    def _set(self, prop: str, value: Any) -> None:
        name = self.name.currentData()
        if self._loading or not name:
            return

        def fn(p) -> None:
            st = p.styles[name]
            setattr(st, prop, value)
            st.user_modified = True
        self.state.edit(f"Change style {name}", fn, kind="settings", merge_key=f"style:{name}:{prop}")

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(QColor(self.color.text()), self, "Text color")
        if c.isValid():
            self._set("color", c.name())

    def _reset(self) -> None:
        name = self.name.currentData()
        if not name:
            return
        base = default_styles().get(name)
        tpl = self.state.templates.get(self.state.project.settings.template) \
            if self.state.project.settings.template else None

        def fn(p) -> None:
            if base is None:
                return
            fresh = StyleDefinition.from_dict(base.to_dict())
            if tpl:
                for k, v in tpl.get("styles", {}).get(name, {}).items():
                    if hasattr(fresh, k) and k not in ("name", "user_modified"):
                        setattr(fresh, k, v)
            fresh.user_modified = False
            p.styles[name] = fresh
        self.state.edit(f"Reset style {name}", fn, kind="settings")
        self.refresh_names()


class PropertiesPanel(QTabWidget):
    templates_requested = Signal()

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.section_tab = SectionTab(state)
        self.block_tab = BlockTab(state)
        self.book_tab = BookTab(state)
        self.styles_tab = StylesTab(state)
        self.addTab(_scroll(self.section_tab), "Section")
        self.addTab(_scroll(self.block_tab), "Block")
        self.addTab(self.book_tab, "Book")
        self.addTab(self.styles_tab, "Styles")
        self.book_tab.templates_requested.connect(self.templates_requested)
        self.setAccessibleName("Properties")
