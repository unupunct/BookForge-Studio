"""Hierarchical book structure view with drag-and-drop reordering."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QInputDialog, QLabel, QMenu,
                               QMessageBox, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..application_state import AppState
from ..services.section_tools import (SectionToolError, merge_with_next, split_by_headings,
                                      split_by_poems)
from ..domain.sections import (ALL_KINDS, BACK_KINDS, FRONT_KINDS, KIND_LABELS, MAIN_KINDS,
                               Section, matter_of)
from . import theme

KIND_ICON = {"front_cover": "▣", "title_page": "▤", "copyright": "©", "dedication": "❤",
             "foreword": "❧", "preface": "❧", "toc": "☰", "part": "❖",
             "chapter": "¶", "section": "§", "appendix": "A", "glossary": "G",
             "bibliography": "B", "index": "I", "acknowledgments": "★", "back_matter": "▢",
             "back_cover": "▣"}


class _Tree(QTreeWidget):
    dropped = Signal()

    def dropEvent(self, e) -> None:
        super().dropEvent(e)
        self.dropped.emit()


class BookNavigator(QWidget):
    section_selected = Signal(str)

    def __init__(self, state: AppState, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = state
        self._rebuilding = False
        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setAccessibleName("Book structure")
        self.tree.setToolTip("Book structure. Drag to reorder, right-click for more, F2 to rename.")
        self.tree.setIndentation(16)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 4)
        self.add_btn = QToolButton(text="+ Add")
        self.add_btn.setToolTip("Add a chapter, section or special page")
        self.add_btn.setPopupMode(QToolButton.InstantPopup)
        self.add_btn.setMenu(self._add_menu())
        up = QToolButton(text="▲")
        up.setToolTip("Move up (Alt+Up)")
        down = QToolButton(text="▼")
        down.setToolTip("Move down (Alt+Down)")
        dup = QToolButton(text="Duplicate")
        dele = QToolButton(text="Remove")
        for w in (self.add_btn, up, down, dup, dele):
            bar.addWidget(w)
        bar.addStretch(1)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        dup.clicked.connect(self.duplicate_current)
        dele.clicked.connect(self.delete_current)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self.tree, 1)

        for seq, fn in (("F2", self.rename_current), ("Alt+Up", lambda: self._move(-1)),
                        ("Alt+Down", lambda: self._move(1)), ("Delete", self.delete_current)):
            a = QAction(self)
            a.setShortcut(seq)
            a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            a.triggered.connect(fn)
            self.tree.addAction(a)

        self.tree.currentItemChanged.connect(self._current_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.dropped.connect(lambda: QTimer.singleShot(0, self._apply_drop))
        self.tree.itemChanged.connect(self._item_edited)
        state.project_changed.connect(self.rebuild)
        state.structure_changed.connect(self.rebuild)

    # ------------------------------------------------------------- building
    def _label(self, s: Section) -> str:
        icon = KIND_ICON.get(s.kind, "·")
        title = s.title.strip() or KIND_LABELS.get(s.kind, s.kind)
        return f"{icon}  {title}" + ("" if s.enabled else "   (hidden)")

    def rebuild(self) -> None:
        keep = self.current_id()
        expanded = set()
        it = QTreeWidgetItem
        for item in self._all_items():
            if item.isExpanded():
                expanded.add(item.data(0, Qt.UserRole))
        self._rebuilding = True
        self.tree.clear()

        def add(parent, s: Section) -> None:
            item = QTreeWidgetItem([self._label(s)])
            item.setData(0, Qt.UserRole, s.id)
            item.setFlags(item.flags() | Qt.ItemIsEditable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
            if not s.enabled:
                item.setForeground(0, QBrush(QColor(theme.TEXT_MUTED)))
            (parent.addChild if parent else self.tree.addTopLevelItem)(item)
            for c in s.children:
                add(item, c)
            if s.id in expanded or not expanded:
                item.setExpanded(True)

        for s in self.state.project.sections:
            add(None, s)
        self._rebuilding = False
        if keep:
            self.select(keep)
        elif self.tree.topLevelItemCount():
            self.select(self._first_content_id())

    def _first_content_id(self) -> str:
        for s in self.state.project.walk():
            if s.kind in ("chapter", "section", "part"):
                return s.id
        return self.state.project.sections[0].id

    def _all_items(self):
        def rec(item):
            yield item
            for i in range(item.childCount()):
                yield from rec(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            yield from rec(self.tree.topLevelItem(i))

    def current_id(self) -> str | None:
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    def select(self, section_id: str) -> None:
        for item in self._all_items():
            if item.data(0, Qt.UserRole) == section_id:
                self._rebuilding = True
                self.tree.setCurrentItem(item)
                self._rebuilding = False
                self.section_selected.emit(section_id)
                return

    def _current_changed(self, cur, prev) -> None:
        if self._rebuilding or cur is None:
            return
        self.section_selected.emit(cur.data(0, Qt.UserRole))

    # ----------------------------------------------------------- operations
    def _add_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Chapter", lambda: self.add_section("chapter"))
        m.addAction("Section (inside current chapter)", lambda: self.add_section("section", child=True))
        m.addAction("Part", lambda: self.add_section("part"))
        front = m.addMenu("Front matter")
        for k in FRONT_KINDS:
            front.addAction(KIND_LABELS[k], lambda k=k: self.add_section(k))
        back = m.addMenu("Back matter")
        for k in BACK_KINDS:
            back.addAction(KIND_LABELS[k], lambda k=k: self.add_section(k))
        return m

    def _insert_position(self, kind: str, child: bool) -> tuple[str | None, int | None]:
        p = self.state.project
        cur = self.current_id()
        if child and cur:
            sec = p.find_section(cur)
            return cur, len(sec.children) if sec else None
        order = {k: i for i, k in enumerate(ALL_KINDS)}
        if kind in FRONT_KINDS or kind in BACK_KINDS:
            for i, s in enumerate(p.sections):
                if order.get(s.kind, 0) > order[kind]:
                    return None, i
            return None, len(p.sections)
        # main content: after the current top-level main section, else before back matter
        if cur:
            loc = p.find_parent(cur)
            if loc:
                siblings, idx = loc
                top = p.sections
                if siblings is top and matter_of(top[idx].kind) == "main":
                    return None, idx + 1
                for i, s in enumerate(top):  # current is nested: insert after its top-level ancestor
                    if any(x.id == cur for x in s.walk()) and matter_of(s.kind) == "main":
                        return None, i + 1
        for i, s in enumerate(p.sections):
            if matter_of(s.kind) == "back":
                return None, i
        return None, len(p.sections)

    def add_section(self, kind: str, child: bool = False) -> None:
        if child and not self.current_id():
            child = False
        title = KIND_LABELS.get(kind, kind)
        if kind in ("chapter", "section", "part"):
            n = sum(1 for s in self.state.project.walk() if s.kind == kind) + 1
            title = f"{title} {n}"
        name, ok = QInputDialog.getText(self, "Add " + KIND_LABELS.get(kind, kind), "Title:", text=title)
        if not ok:
            return
        section = Section(name.strip() or title, kind,
                          in_toc=kind not in ("front_cover", "back_cover", "title_page", "copyright", "toc"),
                          show_title=kind not in ("front_cover", "back_cover", "title_page", "copyright"))
        parent, idx = self._insert_position(kind, child)
        self.state.add_section(section, parent, idx)
        self.select(section.id)

    def rename_current(self) -> None:
        item = self.tree.currentItem()
        if item:
            self.tree.editItem(item, 0)

    def _item_edited(self, item, column) -> None:
        if self._rebuilding:
            return
        sid = item.data(0, Qt.UserRole)
        text = item.text(0)
        for icon in KIND_ICON.values():
            if text.startswith(icon + "  "):
                text = text[len(icon) + 2:]
                break
        text = text.replace("   (hidden)", "").strip()
        self.state.rename_section(sid, text)

    def duplicate_current(self) -> None:
        sid = self.current_id()
        if sid:
            copy = self.state.duplicate_section(sid)
            self.select(copy.id)

    def delete_current(self) -> None:
        sid = self.current_id()
        if not sid:
            return
        sec = self.state.project.find_section(sid)
        if sec is None:
            return
        n_words = self.state.project.word_count(sec)
        extra = f" and its {len(sec.children)} sub-section(s)" if sec.children else ""
        r = QMessageBox.question(
            self, "Remove section",
            f"Remove '{sec.title or KIND_LABELS.get(sec.kind)}'{extra} ({n_words} words)?\n\n"
            "You can undo this with Ctrl+Z. To keep the text but leave it out of the book, "
            "hide the section instead.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.state.remove_section(sid)

    def _move(self, delta: int) -> None:
        sid = self.current_id()
        if sid and self.state.move_section(sid, delta):
            self.select(sid)

    def toggle_enabled(self) -> None:
        sid = self.current_id()
        sec = self.state.project.find_section(sid) if sid else None
        if sec:
            self.state.set_section_attr(sid, enabled=not sec.enabled)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        m = QMenu(self)
        m.addMenu(self._add_menu()).setText("Add")
        if item:
            sid = item.data(0, Qt.UserRole)
            sec = self.state.project.find_section(sid)
            m.addAction("Rename\tF2", self.rename_current)
            m.addAction("Duplicate", self.duplicate_current)
            m.addAction("Hide from book" if sec and sec.enabled else "Include in book", self.toggle_enabled)
            organise = m.addMenu("Organise")
            organise.addAction("Split into one section per poem\u2026", self.split_poems)
            organise.addAction("Split at every Heading 1\u2026", lambda: self.split_headings(1))
            organise.addAction("Split at every Heading 2\u2026", lambda: self.split_headings(2))
            organise.addAction("Merge with the next section\u2026", self.merge_next)
            m.addAction("Move up", lambda: self._move(-1))
            m.addAction("Move down", lambda: self._move(1))
            m.addSeparator()
            m.addAction("Remove…", self.delete_current)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _organise(self, label: str, question: str, fn) -> None:
        sid = self.current_id()
        if not sid:
            return
        if QMessageBox.question(self, label, question + "\n\nYou can undo this with Ctrl+Z.") != QMessageBox.Yes:
            return
        try:
            result = self.state.edit(label, lambda p: fn(p, sid))
        except SectionToolError as e:
            QMessageBox.information(self, label, str(e))
            return
        first = result[0] if isinstance(result, list) and result else result
        self.rebuild()
        if first is not None:
            self.select(first.id)

    def split_poems(self) -> None:
        self._organise("Split into poems", "Make every poem in this section its own section?", split_by_poems)

    def split_headings(self, level: int) -> None:
        self._organise(f"Split at Heading {level}", f"Start a new section at every Heading {level}?",
                       lambda p, sid: split_by_headings(p, sid, level))

    def merge_next(self) -> None:
        self._organise("Merge sections", "Append the next section to this one?", merge_with_next)

    def _apply_drop(self) -> None:
        def rec(item) -> tuple[str, list]:
            return item.data(0, Qt.UserRole), [rec(item.child(i)) for i in range(item.childCount())]
        structure = [rec(self.tree.topLevelItem(i)) for i in range(self.tree.topLevelItemCount())]
        old = [s.id for s in self.state.project.walk()]
        flat = []

        def walk(nodes):
            for sid, kids in nodes:
                flat.append(sid)
                walk(kids)
        walk(structure)
        if sorted(old) != sorted(flat):  # a malformed drop must never lose sections
            self.rebuild()
            return
        keep = self.current_id()
        self.state.reorder_from_tree(structure)
        if keep:
            self.select(keep)
