"""Go to page / chapter / poem (Ctrl+G)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ...application_state import AppState
from ...services.navigation_index import NavEntry, build_index, resolve_page, search_index
from .. import theme

ICONS = {"page": "□", "section": "¶", "heading": "#", "poem": "♪", "recipe": "☕"}


class GoToDialog(QDialog):
    chosen = Signal(object)  # NavEntry

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Go to")
        self.resize(520, 440)
        state.flush()
        self.entries = build_index(state.project, state.layout)
        lay = QVBoxLayout(self)
        hint = QLabel("Type a page number (1, iv), or part of a chapter, heading or poem title.")
        hint.setProperty("muted", True)
        lay.addWidget(hint)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Go to…")
        self.query.setAccessibleName("Go to")
        self.list = QListWidget()
        self.list.setAccessibleName("Matches")
        lay.addWidget(self.query)
        lay.addWidget(self.list, 1)
        self.query.textChanged.connect(self._refresh)
        self.query.returnPressed.connect(self._accept_current)
        self.list.itemActivated.connect(lambda it: self._emit(it.data(Qt.UserRole)))
        self.list.itemDoubleClicked.connect(lambda it: self._emit(it.data(Qt.UserRole)))
        self._refresh()

    def _refresh(self) -> None:
        q = self.query.text()
        shown: list[NavEntry] = []
        page = resolve_page(self.state.layout, q)
        if page:
            shown.append(page)
        shown.extend(search_index(self.entries, q))
        self.list.clear()
        for e in shown:
            page_txt = ""
            if e.page_index is not None and self.state.layout and e.kind != "page":
                lbl = self.state.layout.pages[e.page_index].label
                page_txt = f"   · page {lbl or e.page_index + 1}"
            it = QListWidgetItem(f"{ICONS.get(e.kind, '')}  {e.title}"
                                 + (f"   ({e.detail})" if e.detail and e.kind != "page" else "") + page_txt)
            it.setData(Qt.UserRole, e)
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _accept_current(self) -> None:
        it = self.list.currentItem()
        if it:
            self._emit(it.data(Qt.UserRole))

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Down, Qt.Key_Up):
            self.list.setFocus()
            self.list.keyPressEvent(e)
            return
        super().keyPressEvent(e)

    def _emit(self, entry: NavEntry) -> None:
        self.chosen.emit(entry)
        self.accept()
