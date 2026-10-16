"""Rich-text editor for one section, backed by the structured block model."""
from __future__ import annotations

import re
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRegularExpression, Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QFont, QKeySequence,
                           QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
                           QTextFormat, QTextListFormat)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QTextEdit,
                               QToolBar, QToolButton, QVBoxLayout, QWidget)

from ...application_state import AppState
from ...domain.content_blocks import (Block, ImageBlock, LayoutBlock, PageBreakBlock, ParagraphBlock,
                                      RecipeBlock, SceneBreakBlock, TableBlock, TextBoxBlock, new_id)
from .. import theme
from .block_codec import (LIST_KINDS, P_ALIGN, P_ID, P_KIND, P_KWN, P_LEVEL, P_STYLE, LINE_SEP,
                          blocks_from_document, block_format, char_format, load_blocks,
                          placeholder_text)

ALLOWED_LINK_SCHEMES = ("http://", "https://", "mailto:")
SPECIAL_CHARS = ["„", "”", "“", "«", "»", "‘", "’", "—",
                 "–", "…", "§", "©", "®", "™", "°", "±",
                 "×", "÷", "•", "·", "ă", "â", "î", "ș",
                 "ț", "Ă", "Â", "Î", "Ș", "Ț", "é", "è",
                 "ü", "ö", "ä", "ß", "ñ", "ç", "€", "£"]

BLOCK_STYLES = [("Body text", "paragraph", 1), ("Heading 1", "heading", 1),
                ("Heading 2", "heading", 2), ("Heading 3", "heading", 3),
                ("Heading 4", "heading", 4), ("Block quote", "quote", 1),
                ("Code block", "code", 1), ("Poetry", "poetry", 1),
                ("Bullet list", "list_bullet", 1), ("Numbered list", "list_number", 1),
                ("Scene break", "scene", 1)]


class _Edit(QTextEdit):
    placeholder_activated = Signal(str)  # block id
    block_protected = Signal()

    def __init__(self, owner: "ChapterEditor"):
        super().__init__(owner)
        self.owner = owner
        self.setAcceptRichText(False)
        self.setUndoRedoEnabled(True)
        self.setTabChangesFocus(False)
        self.setAccessibleName("Chapter text editor")
        self.setStyleSheet(f"QTextEdit {{ background: {theme.PANEL}; border: 0; padding: 18px 28px; "
                           f"selection-background-color: {theme.ACCENT_DIM}; }}")
        self.document().setDocumentMargin(12)
        self.setLineWrapMode(QTextEdit.WidgetWidth)

    # Pasting never imports foreign formatting or markup.
    def insertFromMimeData(self, source) -> None:
        if source.hasText():
            text = source.text().replace("\r\n", "\n").replace("\r", "\n")
            kind = self.owner.current_kind()
            if kind in ("code", "poetry"):
                self.textCursor().insertText(text.replace("\n", LINE_SEP))
            else:
                parts = text.split("\n")
                cur = self.textCursor()
                cur.beginEditBlock()
                for i, part in enumerate(parts):
                    if i:
                        cur.insertBlock()
                    cur.insertText(part)
                cur.endEditBlock()
        elif source.hasImage() or source.hasUrls():
            self.owner.message.emit("Paste an image with Insert › Image so it is stored in the project")

    def _block_kind_at(self, cursor: QTextCursor) -> str:
        v = cursor.blockFormat().property(P_KIND)
        return str(v) if v else "paragraph"

    def keyPressEvent(self, e) -> None:
        cur = self.textCursor()
        kind = self._block_kind_at(cur)
        edit_keys = e.text() and not (e.modifiers() & (Qt.ControlModifier | Qt.AltModifier)) \
            or e.key() in (Qt.Key_Backspace, Qt.Key_Delete, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab)
        if kind == "placeholder" and edit_keys:
            if e.key() in (Qt.Key_Backspace, Qt.Key_Delete):
                self.owner.delete_placeholder(cur.block())
            elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.owner.activate_placeholder(cur.block())
            else:
                self.block_protected.emit()
            return
        if edit_keys and self.owner.is_locked(cur.block()):
            self.owner.message.emit("This block is locked. Unlock it in the Block properties to edit.")
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            if kind in ("code", "poetry"):
                # Enter inserts a line break inside the block; Ctrl+Enter starts a new block.
                if not (e.modifiers() & Qt.ControlModifier):
                    cur.insertText(LINE_SEP)
                    return
            if kind == "scene":
                super().keyPressEvent(e)
                self.owner.reset_to_paragraph(self.textCursor().block())
                return
            at_end = cur.atBlockEnd() and not cur.hasSelection()
            super().keyPressEvent(e)
            if kind in ("heading", "quote_attr", "poem_title", "exercise") and at_end:
                self.owner.reset_to_paragraph(self.textCursor().block())
            return
        super().keyPressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        cur = self.cursorForPosition(e.position().toPoint())
        if self._block_kind_at(cur) == "placeholder":
            self.owner.activate_placeholder(cur.block())
            return
        super().mouseDoubleClickEvent(e)


class FindBar(QWidget):
    def __init__(self, editor: "ChapterEditor"):
        super().__init__(editor)
        self.editor = editor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.find = QLineEdit(placeholderText="Find")
        self.find.setAccessibleName("Find text")
        self.repl = QLineEdit(placeholderText="Replace with")
        self.repl.setAccessibleName("Replacement text")
        self.case = QCheckBox("Aa")
        self.case.setToolTip("Match case")
        self.word = QCheckBox("Word")
        self.word.setToolTip("Whole words only")
        prev = QPushButton("▲")
        prev.setToolTip("Find previous (Shift+F3)")
        nxt = QPushButton("▼")
        nxt.setToolTip("Find next (F3)")
        rep = QPushButton("Replace")
        rep_all = QPushButton("Replace all")
        close = QPushButton("✕")
        close.setToolTip("Close (Esc)")
        self.status = QLabel("")
        theme.set_muted(self.status)
        for w in (self.find, self.repl, self.case, self.word, prev, nxt, rep, rep_all, self.status):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(close)
        self.find.returnPressed.connect(lambda: self.go(False))
        self.find.textChanged.connect(lambda _: self.go(False, keep=True))
        nxt.clicked.connect(lambda: self.go(False))
        prev.clicked.connect(lambda: self.go(True))
        rep.clicked.connect(self.replace_one)
        rep_all.clicked.connect(self.replace_all)
        close.clicked.connect(self.hide)
        self.setVisible(False)

    def flags(self, backward: bool = False) -> QTextDocument.FindFlag:
        f = QTextDocument.FindFlag(0)
        if self.case.isChecked():
            f |= QTextDocument.FindCaseSensitively
        if self.word.isChecked():
            f |= QTextDocument.FindWholeWords
        if backward:
            f |= QTextDocument.FindBackward
        return f

    def go(self, backward: bool, keep: bool = False) -> bool:
        text = self.find.text()
        if not text:
            self.status.setText("")
            return False
        ed = self.editor.edit
        cur = ed.textCursor()
        if keep:
            cur.setPosition(cur.selectionStart())
        found = ed.document().find(text, cur, self.flags(backward))
        if found.isNull():
            wrap = QTextCursor(ed.document())
            if backward:
                wrap.movePosition(QTextCursor.End)
            found = ed.document().find(text, wrap, self.flags(backward))
        if found.isNull():
            self.status.setText("Not found")
            return False
        ed.setTextCursor(found)
        self.status.setText("")
        return True

    def replace_one(self) -> None:
        ed = self.editor.edit
        cur = ed.textCursor()
        if cur.hasSelection() and self._selection_matches(cur):
            if self.editor.is_locked(cur.block()) or cur.blockFormat().property(P_KIND) == "placeholder":
                self.status.setText("Locked block skipped")
            else:
                cur.insertText(self.repl.text())
        self.go(False)

    def _selection_matches(self, cur: QTextCursor) -> bool:
        a, b = cur.selectedText(), self.find.text()
        return a == b if self.case.isChecked() else a.lower() == b.lower()

    def replace_all(self) -> None:
        text = self.find.text()
        if not text:
            return
        ed = self.editor.edit
        doc = ed.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        n = skipped = 0
        pos = QTextCursor(doc)
        while True:
            found = doc.find(text, pos, self.flags())
            if found.isNull():
                break
            pos = found
            if self.editor.is_locked(found.block()) or found.blockFormat().property(P_KIND) == "placeholder":
                skipped += 1
                continue
            found.insertText(self.repl.text())
            pos = found
            n += 1
        cur.endEditBlock()
        self.status.setText(f"{n} replaced" + (f", {skipped} locked skipped" if skipped else ""))


class ChapterEditor(QWidget):
    edited = Signal()                 # text synchronised into the model
    message = Signal(str)
    block_context_changed = Signal()  # cursor moved to a different kind of block

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self.section_id: str | None = None
        self._loading = False
        self._pending: dict[str, Block] = {}
        self._changed = False
        self.edit = _Edit(self)
        self.find_bar = FindBar(self)
        self._build_toolbar()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.toolbar)
        lay.addWidget(self.find_bar)
        lay.addWidget(self.edit, 1)
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(450)
        self._sync_timer.timeout.connect(self.flush)
        self.edit.document().contentsChanged.connect(self._on_changed)
        self.edit.cursorPositionChanged.connect(self._on_cursor)
        self.edit.currentCharFormatChanged.connect(lambda _: self._update_actions())
        self.edit.block_protected.connect(lambda: self.message.emit("This block is edited with its dialog (double-click)"))
        state.add_flush_hook(self.flush)

    # ------------------------------------------------------------ toolbar
    def _act(self, text: str, tip: str, slot: Callable, shortcut=None, checkable=False) -> QAction:
        a = QAction(text, self)
        a.setToolTip(tip + (f" ({QKeySequence(shortcut).toString()})" if shortcut else ""))
        a.setStatusTip(tip)
        if shortcut:
            a.setShortcut(shortcut)
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_toolbar(self) -> None:
        tb = QToolBar("Format", self)
        tb.setMovable(False)
        self.toolbar = tb
        self.style_combo = QComboBox()
        self.style_combo.setAccessibleName("Block style")
        self.style_combo.setToolTip("Block style: heading level, quote, code, poetry or list")
        for label, kind, level in BLOCK_STYLES:
            self.style_combo.addItem(label, (kind, level))
        self.style_combo.activated.connect(self._style_chosen)
        tb.addWidget(self.style_combo)
        tb.addSeparator()
        self.act_bold = self._act("B", "Bold", self.toggle_bold, QKeySequence.Bold, True)
        self.act_italic = self._act("I", "Italic", self.toggle_italic, QKeySequence.Italic, True)
        self.act_under = self._act("U", "Underline", self.toggle_underline, QKeySequence.Underline, True)
        self.act_code = self._act("</>", "Inline code", self.toggle_code, "Ctrl+Shift+K", True)
        f = self.act_bold.font()
        f.setBold(True)
        self.act_bold.setFont(f)
        f = self.act_italic.font()
        f.setItalic(True)
        self.act_italic.setFont(f)
        for a in (self.act_bold, self.act_italic, self.act_under, self.act_code):
            tb.addAction(a)
        tb.addAction(self._act("Link", "Add or edit a hyperlink", self.edit_link, "Ctrl+K"))
        tb.addAction(self._act("Unlink", "Remove hyperlink", self.remove_link))
        tb.addSeparator()
        tb.addAction(self._act("x²", "Superscript", lambda: self.toggle_vertical(True)))
        tb.addAction(self._act("x₂", "Subscript", lambda: self.toggle_vertical(False)))
        tb.addAction(self._act("S̶", "Strikethrough", self.toggle_strike))
        for label, name, tip in (("≡L", "left", "Align left"), ("≡C", "center", "Center"),
                                 ("≡R", "right", "Align right"), ("≡J", "justify", "Justify"),
                                 ("≡∖", "", "Use the template's alignment")):
            tb.addAction(self._act(label, tip, lambda _=False, n=name: self.set_alignment(n)))
        tb.addSeparator()
        tb.addAction(self._act("• List", "Bullet list", lambda: self.set_block_kind("list_bullet")))
        tb.addAction(self._act("1. List", "Numbered list", lambda: self.set_block_kind("list_number")))
        tb.addSeparator()
        self.insert_menu = QMenu("Insert", self)
        self.insert_menu.addAction("Image…", self.insert_image)
        self.insert_menu.addAction("Table…", self.insert_table)
        self.insert_menu.addAction("Page layout (photo page, image + text, quote)…", self.insert_layout)
        self.insert_menu.addAction("Text box (pinned to the page)…", self.insert_textbox)
        self.insert_menu.addAction("Page break", lambda: self.insert_block(PageBreakBlock()))
        self.insert_menu.addAction("Blank page", lambda: self.insert_block(PageBreakBlock(blank=True)))
        self.insert_menu.addAction("Scene separator", lambda: self.insert_block(SceneBreakBlock()))
        self.insert_menu.addAction("Recipe…", self.insert_recipe)
        self.insert_menu.addSeparator()
        for label, kind in (("Learning objective", "objective"), ("Definition", "definition"),
                            ("Example", "example"), ("Exercise", "exercise"),
                            ("Question", "question"), ("Answer", "answer"), ("Note", "note"),
                            ("Warning", "warning")):
            self.insert_menu.addAction(label, lambda k=kind: self.insert_exercise(k))
        ib = QToolButton()
        ib.setText("Insert ▾")
        ib.setToolTip("Insert image, table, page break, recipe or textbook element")
        ib.setPopupMode(QToolButton.InstantPopup)
        ib.setMenu(self.insert_menu)
        tb.addWidget(ib)
        self.special_menu = QMenu("Special characters", self)
        for ch in SPECIAL_CHARS:
            self.special_menu.addAction(ch, lambda c=ch: self.edit.textCursor().insertText(c))
        sb = QToolButton()
        sb.setText("Ω")
        sb.setToolTip("Insert special character")
        sb.setPopupMode(QToolButton.InstantPopup)
        sb.setMenu(self.special_menu)
        tb.addWidget(sb)
        tb.addSeparator()
        tb.addAction(self._act("Find", "Find and replace in this chapter", self.show_find, QKeySequence.Find))
        self.addAction(self._act("", "Find next", lambda: self.find_bar.go(False), "F3"))
        self.addAction(self._act("", "Find previous", lambda: self.find_bar.go(True), "Shift+F3"))
        esc = QAction(self)
        esc.setShortcut("Esc")
        esc.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        esc.triggered.connect(lambda: (self.find_bar.hide(), self.edit.setFocus()))
        self.addAction(esc)

    # -------------------------------------------------------------- loading
    def section(self):
        return self.state.project.find_section(self.section_id) if self.section_id else None

    def load_section(self, section_id: str | None) -> None:
        self.flush()
        self.section_id = section_id
        sec = self.section()
        self._loading = True
        self._pending.clear()
        if sec is None:
            self.edit.document().clear()
            self.edit.setEnabled(False)
        else:
            self.edit.setEnabled(True)
            load_blocks(self.edit.document(), sec.blocks, self.state.project)
            self.edit.moveCursor(QTextCursor.Start)
        self._loading = False
        self._changed = False
        self._update_actions()

    def block_changed_externally(self, block_id: str) -> None:
        """A block was changed outside the editor (dragged in the preview): refresh the editor's own copy."""
        sec = self.section()
        mb = next((b for b in sec.blocks if b.id == block_id), None) if sec else None
        if mb is None:
            return
        if block_id in self._pending:
            self._pending[block_id] = mb
        b = self.edit.document().begin()
        while b.isValid():
            if str(b.blockFormat().property(P_ID) or "") == block_id and str(b.blockFormat().property(P_KIND) or "") == "placeholder":
                self._refresh_placeholder(b, mb)
                break
            b = b.next()

    def reload_if_stale(self) -> None:
        """Called after undo/redo of structure: reload from the (replaced) model."""
        self._changed = False
        self.load_section(self.section_id)

    # --------------------------------------------------------------- syncing
    def _on_changed(self) -> None:
        if self._loading:
            return
        self._changed = True
        self.state.mark_dirty()
        self._sync_timer.start()

    def flush(self) -> None:
        self._sync_timer.stop()
        sec = self.section()
        if sec is None or not self._changed:
            return
        originals = {b.id: b for b in sec.blocks}
        originals.update(self._pending)
        sec.blocks = blocks_from_document(self.edit.document(), originals)
        self._changed = False
        self.state.content_edited()
        self.edited.emit()

    # ------------------------------------------------------------ cursor/state
    def current_kind(self) -> str:
        v = self.edit.textCursor().blockFormat().property(P_KIND)
        return str(v) if v else "paragraph"

    def current_block_id(self) -> str | None:
        v = self.edit.textCursor().blockFormat().property(P_ID)
        return str(v) if v else None

    def _on_cursor(self) -> None:
        self._update_actions()
        self.block_context_changed.emit()

    def _update_actions(self) -> None:
        fmt = self.edit.currentCharFormat()
        kind_now = self.current_kind()
        self.act_bold.setEnabled(kind_now not in ("heading", "code", "placeholder"))
        self.act_italic.setEnabled(kind_now not in ("quote", "code", "placeholder"))
        for act, on in ((self.act_bold, fmt.fontWeight() >= 600 and kind_now != "heading"), (self.act_italic, fmt.fontItalic() and kind_now != "quote"),
                        (self.act_under, fmt.fontUnderline() and not fmt.isAnchor()),
                        (self.act_code, bool(fmt.property(_P_CODE)))):
            act.blockSignals(True)
            act.setChecked(bool(on))
            act.blockSignals(False)
        kind = self.current_kind()
        level = self.edit.textCursor().blockFormat().property(P_LEVEL)
        try:
            level = int(level or 1)
        except (TypeError, ValueError):
            level = 1
        for i in range(self.style_combo.count()):
            k, lv = self.style_combo.itemData(i)
            if k == kind and (kind != "heading" or lv == level):
                self.style_combo.blockSignals(True)
                self.style_combo.setCurrentIndex(i)
                self.style_combo.blockSignals(False)
                break

    # ------------------------------------------------------------- formatting
    def _merge(self, fmt: QTextCharFormat) -> None:
        self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def toggle_bold(self) -> None:
        if self.current_kind() in ("heading", "code", "placeholder"):
            return
        f = QTextCharFormat()
        f.setFontWeight(QFont.Normal if self.edit.currentCharFormat().fontWeight() >= 600 else QFont.Bold)
        self._merge(f)

    def toggle_italic(self) -> None:
        if self.current_kind() in ("quote", "code", "placeholder"):
            return
        f = QTextCharFormat()
        f.setFontItalic(not self.edit.currentCharFormat().fontItalic())
        self._merge(f)

    def toggle_underline(self) -> None:
        f = QTextCharFormat()
        f.setFontUnderline(not self.edit.currentCharFormat().fontUnderline())
        self._merge(f)

    def toggle_code(self) -> None:
        cur = bool(self.edit.currentCharFormat().property(_P_CODE))
        f = QTextCharFormat()
        if cur:
            f.setProperty(_P_CODE, False)
            f.setFontFamilies(["Georgia"])
            f.setBackground(QBrush(Qt.NoBrush))
        else:
            f.setProperty(_P_CODE, True)
            f.setFontFamilies(["Consolas"])
            f.setBackground(QBrush(QColor(theme.SURFACE_HI)))
        self._merge(f)

    def toggle_vertical(self, sup: bool) -> None:
        cur = self.edit.currentCharFormat().verticalAlignment()
        want = QTextCharFormat.AlignSuperScript if sup else QTextCharFormat.AlignSubScript
        f = QTextCharFormat()
        f.setVerticalAlignment(QTextCharFormat.AlignNormal if cur == want else want)
        self._merge(f)

    def toggle_strike(self) -> None:
        f = QTextCharFormat()
        f.setFontStrikeOut(not self.edit.currentCharFormat().fontStrikeOut())
        self._merge(f)

    def set_alignment(self, align: str) -> None:
        """Alignment override for the selected paragraphs/poems ("" = follow the template)."""
        qt = {"left": Qt.AlignLeft, "center": Qt.AlignHCenter, "right": Qt.AlignRight,
              "justify": Qt.AlignJustify}.get(align, Qt.AlignLeft)
        cur = QTextCursor(self.edit.document())
        cur.beginEditBlock()
        for b in self._selected_blocks():
            if b.blockFormat().property(P_KIND) not in ("paragraph", "poetry"):
                continue
            c = QTextCursor(b)
            bf = QTextBlockFormat()
            bf.setProperty(P_ALIGN, align)
            bf.setAlignment(qt)
            c.mergeBlockFormat(bf)
        cur.endEditBlock()
        self.edit.setFocus()

    def edit_link(self) -> None:
        cur = self.edit.textCursor()
        existing = cur.charFormat().anchorHref() if cur.charFormat().isAnchor() else ""
        url, ok = QInputDialog.getText(self, "Hyperlink", "Address (http://, https:// or mailto:):",
                                       QLineEdit.Normal, existing)
        if not ok or not url.strip():
            return
        url = url.strip()
        if not url.lower().startswith(ALLOWED_LINK_SCHEMES):
            url = "https://" + url
        if not cur.hasSelection():
            cur.insertText(url)
            cur.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(url))
        f = QTextCharFormat()
        f.setAnchor(True)
        f.setAnchorHref(url)
        f.setForeground(QBrush(QColor(theme.ACCENT_HI)))
        f.setFontUnderline(True)
        cur.mergeCharFormat(f)
        self.edit.setTextCursor(cur)

    def remove_link(self) -> None:
        cur = self.edit.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.WordUnderCursor)
        f = QTextCharFormat()
        f.setAnchor(False)
        f.setAnchorHref("")
        f.setFontUnderline(False)
        f.setForeground(QBrush(QColor(theme.TEXT)))
        cur.mergeCharFormat(f)

    # ---------------------------------------------------------------- blocks
    def _style_chosen(self, index: int) -> None:
        kind, level = self.style_combo.itemData(index)
        self.set_block_kind(kind, level)

    def _selected_blocks(self):
        cur = self.edit.textCursor()
        doc = self.edit.document()
        first = doc.findBlock(cur.selectionStart())
        last = doc.findBlock(cur.selectionEnd())
        b = first
        while b.isValid():
            yield b
            if b == last:
                break
            b = b.next()

    def set_block_kind(self, kind: str, level: int = 1) -> None:
        doc = self.edit.document()
        blocks = [b for b in self._selected_blocks()
                  if b.blockFormat().property(P_KIND) != "placeholder" and not self.is_locked(b)]
        if not blocks:
            return
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        # Several lines turned into poetry/code become ONE block so line breaks are kept.
        if kind in ("poetry", "code") and len(blocks) > 1:
            text = LINE_SEP.join(b.text() for b in blocks)
            first = QTextCursor(blocks[0])
            first.setPosition(blocks[0].position())
            first.setPosition(blocks[-1].position() + blocks[-1].length() - 1, QTextCursor.KeepAnchor)
            first.removeSelectedText()
            first.insertText(text)
            blocks = [doc.findBlock(first.position())]
        lst_obj = None
        for b in blocks:
            c = QTextCursor(b)
            old = b.blockFormat()
            bid = old.property(P_ID) or new_id()
            if b.textList() is not None and kind not in LIST_KINDS:
                b.textList().remove(b)
            bf = block_format(kind, level)
            bf.setProperty(P_KIND, kind)
            bf.setProperty(P_ID, bid)
            bf.setProperty(P_LEVEL, level)
            bf.setProperty(P_KWN, bool(old.property(P_KWN)))
            c.setBlockFormat(bf)
            if kind in LIST_KINDS:
                if lst_obj is None:
                    lf = QTextListFormat()
                    lf.setStyle(QTextListFormat.ListDecimal if kind == "list_number"
                                else QTextListFormat.ListDisc)
                    lf.setIndent(1)
                    lst_obj = c.createList(lf)
                else:
                    lst_obj.add(b)
            c.select(QTextCursor.BlockUnderCursor)
            if c.hasSelection():
                c.setPosition(b.position())
                c.setPosition(b.position() + b.length() - 1, QTextCursor.KeepAnchor)
            c.setCharFormat(char_format(kind, level))
            c.setBlockCharFormat(char_format(kind, level))
        cur.endEditBlock()
        self._update_actions()
        self.edit.setFocus()

    def reset_to_paragraph(self, block) -> None:
        c = QTextCursor(block)
        bf = block_format("paragraph")
        bf.setProperty(P_KIND, "paragraph")
        bf.setProperty(P_ID, new_id())
        bf.setProperty(P_LEVEL, 1)
        if block.textList() is not None:
            block.textList().remove(block)
        c.setBlockFormat(bf)
        c.setBlockCharFormat(char_format("paragraph", 1))
        self.edit.setCurrentCharFormat(char_format("paragraph", 1))

    def set_block_property(self, **props) -> None:
        """keep_with_next / style override for the block under the cursor."""
        c = self.edit.textCursor()
        bf = QTextBlockFormat()
        if "keep_with_next" in props:
            bf.setProperty(P_KWN, bool(props["keep_with_next"]))
        if "style" in props:
            bf.setProperty(P_STYLE, props["style"] or "")
        if "level" in props and self.current_kind() == "heading":
            self.set_block_kind("heading", int(props["level"]))
            return
        c.mergeBlockFormat(bf)

    def block_properties(self) -> dict:
        bf = self.edit.textCursor().blockFormat()
        style = bf.property(P_STYLE)
        try:
            level = int(bf.property(P_LEVEL) or 1)
        except (TypeError, ValueError):
            level = 1
        return {"kind": self.current_kind(), "level": level,
                "keep_with_next": bool(bf.property(P_KWN)),
                "style": "" if style in (None, "[]") else str(style),
                "id": self.current_block_id(),
                "locked": self.is_locked(self.edit.textCursor().block())}

    def _model_block(self, block_id: str | None) -> Block | None:
        sec = self.section()
        if not block_id:
            return None
        if block_id in self._pending:
            return self._pending[block_id]
        if sec:
            return next((b for b in sec.blocks if b.id == block_id), None)
        return None

    def current_model_block(self) -> Block | None:
        self.flush()
        return self._model_block(self.current_block_id())

    def set_model_property(self, **props) -> None:
        """Change a non-text property of the block under the cursor (e.g. one poem per page)."""
        mb = self.current_model_block()
        if mb is None:
            return
        for k, v in props.items():
            if hasattr(mb, k):
                setattr(mb, k, v)
        self.state.content_edited()
        if "title" in props:  # a poem title is a separate text block in the editor
            keep = self.current_block_id()
            self.load_section(self.section_id)
            if keep:
                self.scroll_to_block(keep)
        elif isinstance(mb, PageBreakBlock):
            self._refresh_placeholder(self.edit.textCursor().block(), mb)

    def is_locked(self, block) -> bool:
        bid = block.blockFormat().property(P_ID)
        mb = self._model_block(str(bid)) if bid else None
        return bool(mb and mb.locked)

    def set_locked(self, locked: bool) -> None:
        self.flush()
        mb = self._model_block(self.current_block_id())
        if mb:
            mb.locked = locked
            self.state.mark_dirty()

    # -------------------------------------------------------- model blocks
    def insert_block(self, block: Block) -> None:
        """Insert a non-text block (image, table, page break...) after the current block."""
        self._pending[block.id] = block
        doc = self.edit.document()
        cur = self.edit.textCursor()
        cur.movePosition(QTextCursor.EndOfBlock)
        cur.beginEditBlock()
        cur.insertBlock(QTextBlockFormat(), QTextCharFormat())
        if isinstance(block, SceneBreakBlock):
            kind, text = "scene", block.glyph
        else:
            kind, text = "placeholder", placeholder_text(block, self.state.project)
        bf = block_format(kind)
        bf.setProperty(P_KIND, kind)
        bf.setProperty(P_ID, block.id)
        cur.setBlockFormat(bf)
        cur.setBlockCharFormat(char_format(kind, 1))
        cur.insertText(text, char_format(kind, 1))
        # a normal paragraph after it so typing can continue
        nxt = cur.block().next()
        if not nxt.isValid():
            cur.insertBlock(QTextBlockFormat(), QTextCharFormat())
            pb = block_format("paragraph")
            pb.setProperty(P_KIND, "paragraph")
            pb.setProperty(P_ID, new_id())
            cur.setBlockFormat(pb)
            cur.setBlockCharFormat(char_format("paragraph", 1))
        cur.endEditBlock()
        self.edit.setTextCursor(cur)
        self.edit.setFocus()
        self.flush()

    def insert_exercise(self, kind: str) -> None:
        from ...domain.content_blocks import ExerciseBlock
        self.flush()
        title, ok = QInputDialog.getText(self, "Textbook element", "Title (optional):")
        if not ok:
            return
        blk = ExerciseBlock(kind=kind, title=title.strip())
        cur = self.edit.textCursor()
        cur.movePosition(QTextCursor.EndOfBlock)
        cur.beginEditBlock()
        cur.insertBlock(QTextBlockFormat(), QTextCharFormat())
        import json
        bf = block_format("exercise")
        bf.setProperty(P_KIND, "exercise")
        bf.setProperty(P_ID, blk.id)
        bf.setProperty(_P_DATA, json.dumps({"kind": kind, "title": blk.title}))
        cur.setBlockFormat(bf)
        cur.setBlockCharFormat(char_format("exercise", 1))
        cur.endEditBlock()
        self.edit.setTextCursor(cur)
        self.edit.setFocus()

    def insert_image(self) -> None:
        from .block_dialogs import choose_and_add_image
        self.flush()
        blk = choose_and_add_image(self, self.state.project)
        if blk:
            blk.width_pct = self.state.project.settings.image_default_width_pct
            self.insert_block(blk)

    def insert_table(self) -> None:
        from .block_dialogs import TableDialog
        dlg = TableDialog(self, TableBlock(rows=[["", ""], ["", ""]], header_rows=1))
        if dlg.exec():
            self.insert_block(dlg.result_block())

    def insert_layout(self) -> None:
        from .block_dialogs import LayoutDialog
        self.flush()
        dlg = LayoutDialog(self, LayoutBlock(), self.state.project)
        if dlg.exec():
            self.insert_block(dlg.result_block())

    def insert_textbox(self) -> None:
        from .block_dialogs import TextBoxDialog
        self.flush()
        dlg = TextBoxDialog(self, TextBoxBlock(text="Text", px=0.15, py=0.15, pw=0.4, ph=0.12))
        if dlg.exec():
            self.insert_block(dlg.result_block())

    def insert_recipe(self) -> None:
        from .block_dialogs import RecipeDialog
        dlg = RecipeDialog(self, RecipeBlock(), self.state.project)
        if dlg.exec():
            self.insert_block(dlg.result_block())

    def activate_placeholder(self, qblock) -> None:
        from .block_dialogs import ImageDialog, LayoutDialog, RecipeDialog, TableDialog, TextBoxDialog
        bid = qblock.blockFormat().property(P_ID)
        mb = self._model_block(str(bid)) if bid else None
        if mb is None:
            return
        dlg = None
        if isinstance(mb, ImageBlock):
            dlg = ImageDialog(self, mb, self.state.project)
        elif isinstance(mb, TableBlock):
            dlg = TableDialog(self, mb)
        elif isinstance(mb, RecipeBlock):
            dlg = RecipeDialog(self, mb, self.state.project)
        elif isinstance(mb, TextBoxBlock):
            dlg = TextBoxDialog(self, mb)
        elif isinstance(mb, LayoutBlock):
            dlg = LayoutDialog(self, mb, self.state.project)
        elif isinstance(mb, PageBreakBlock):
            blank = QMessageBox.question(self, "Page break", "Insert a blank page here as well?\n"
                                         "Yes = blank page, No = ordinary page break",
                                         QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if blank != QMessageBox.Cancel:
                mb.blank = blank == QMessageBox.Yes
                self._refresh_placeholder(qblock, mb)
            return
        if dlg and dlg.exec():
            new = dlg.result_block()
            sec = self.section()
            for i, b in enumerate(sec.blocks):
                if b.id == mb.id:
                    sec.blocks[i] = new
            self._pending[new.id] = new
            self._refresh_placeholder(qblock, new)

    def _refresh_placeholder(self, qblock, mb: Block) -> None:
        c = QTextCursor(qblock)
        c.beginEditBlock()
        c.setPosition(qblock.position())
        c.setPosition(qblock.position() + qblock.length() - 1, QTextCursor.KeepAnchor)
        c.insertText(placeholder_text(mb, self.state.project), char_format("placeholder", 1))
        c.endEditBlock()

    def delete_placeholder(self, qblock) -> None:
        r = QMessageBox.question(self, "Delete block", "Delete this block (image, table or page "
                                 "break) from the chapter? You can undo with Ctrl+Z.")
        if r != QMessageBox.Yes:
            return
        c = QTextCursor(qblock)
        c.beginEditBlock()
        c.select(QTextCursor.BlockUnderCursor)
        if not c.hasSelection():  # first block of the document
            c.setPosition(qblock.position())
            c.setPosition(qblock.position() + qblock.length(), QTextCursor.KeepAnchor)
        c.removeSelectedText()
        c.endEditBlock()

    # ------------------------------------------------------------- navigation
    def show_find(self) -> None:
        self.find_bar.setVisible(True)
        cur = self.edit.textCursor()
        if cur.hasSelection():
            self.find_bar.find.setText(cur.selectedText())
        self.find_bar.find.setFocus()
        self.find_bar.find.selectAll()

    def scroll_to_block(self, block_id: str, select_text: str | None = None) -> bool:
        doc = self.edit.document()
        b = doc.begin()
        while b.isValid():
            if str(b.blockFormat().property(P_ID) or "") == block_id:
                cur = QTextCursor(b)
                if select_text:
                    f = doc.find(select_text, cur)
                    if not f.isNull() and f.blockNumber() == b.blockNumber():
                        cur = f
                self.edit.setTextCursor(cur)
                self.edit.ensureCursorVisible()
                self.edit.setFocus()
                return True
            b = b.next()
        return False

    def stats(self) -> tuple[int, int]:
        text = self.edit.document().toPlainText()
        return len(text.split()), len(text)

    def undo(self) -> None:
        self.edit.undo()

    def redo(self) -> None:
        self.edit.redo()


from .block_codec import P_CODE as _P_CODE, P_DATA as _P_DATA  # noqa: E402
