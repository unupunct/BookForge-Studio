"""Book-wide search and replace."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from ...application_state import AppState
from ...services.search_service import (SearchHit, SearchOptions, replace_in_book, replace_one,
                                        search_book)
from .. import theme


class SearchDialog(QDialog):
    navigate = Signal(str, str, str)  # section id, block id, matched text
    replaced = Signal()  # the model changed: open editors must reload

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.hits: list[SearchHit] = []
        self.current_section_id: str | None = None
        self.setWindowTitle("Search the book")
        self.setModal(False)
        self.resize(620, 520)
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        self.find = QLineEdit()
        self.find.setPlaceholderText("Find")
        self.find.setAccessibleName("Search text")
        self.repl = QLineEdit()
        self.repl.setPlaceholderText("Replace with")
        self.repl.setAccessibleName("Replacement")
        self.scope = QComboBox()
        self.scope.addItem("Whole book", False)
        self.scope.addItem("Current chapter", True)
        self.case = QCheckBox("Match case")
        self.word = QCheckBox("Whole words")
        self.headings = QCheckBox("Headings")
        self.headings.setChecked(True)
        self.code = QCheckBox("Code blocks")
        self.code.setChecked(True)
        self.captions = QCheckBox("Captions")
        self.captions.setChecked(True)
        self.tables = QCheckBox("Tables")
        self.tables.setChecked(True)
        self.hidden = QCheckBox("Hidden sections")
        grid.addWidget(QLabel("Find"), 0, 0)
        grid.addWidget(self.find, 0, 1, 1, 3)
        grid.addWidget(QLabel("Replace"), 1, 0)
        grid.addWidget(self.repl, 1, 1, 1, 3)
        grid.addWidget(QLabel("Search in"), 2, 0)
        grid.addWidget(self.scope, 2, 1)
        grid.addWidget(self.case, 2, 2)
        grid.addWidget(self.word, 2, 3)
        for i, w in enumerate((self.headings, self.code, self.captions, self.tables)):
            grid.addWidget(w, 3, i)
        grid.addWidget(self.hidden, 4, 0)
        lay.addLayout(grid)
        bar = QHBoxLayout()
        self.find_btn = QPushButton("Find all")
        theme.accent_button(self.find_btn)
        self.rep_btn = QPushButton("Replace selected")
        self.rep_all = QPushButton("Replace all…")
        bar.addWidget(self.find_btn)
        bar.addWidget(self.rep_btn)
        bar.addWidget(self.rep_all)
        bar.addStretch(1)
        lay.addLayout(bar)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Chapter", "Where", "Match"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 90)
        self.tree.setAccessibleName("Search results")
        lay.addWidget(self.tree, 1)
        self.status = QLabel("")
        theme.set_muted(self.status)
        lay.addWidget(self.status)
        self.find.returnPressed.connect(self.run_search)
        self.find_btn.clicked.connect(self.run_search)
        self.rep_btn.clicked.connect(self.replace_selected)
        self.rep_all.clicked.connect(self.replace_everything)
        self.tree.itemActivated.connect(self._open)
        self.tree.itemDoubleClicked.connect(self._open)

    def options(self) -> SearchOptions:
        return SearchOptions(
            case_sensitive=self.case.isChecked(), whole_word=self.word.isChecked(),
            current_section_id=self.current_section_id if self.scope.currentData() else None,
            headings=self.headings.isChecked(), code=self.code.isChecked(),
            captions=self.captions.isChecked(), tables=self.tables.isChecked(),
            include_hidden=self.hidden.isChecked())

    def run_search(self) -> None:
        self.state.flush()
        self.hits = search_book(self.state.project, self.find.text(), self.options())
        self.tree.clear()
        names = {"heading": "Heading", "paragraph": "Text", "code": "Code", "table": "Table",
                 "image": "Caption", "poetry": "Poetry", "list": "List", "quote": "Quote"}
        for h in self.hits:
            where = "Caption" if h.field == "caption" else names.get(h.block_type, h.block_type)
            it = QTreeWidgetItem([h.section_title, where + (" \U0001F512" if h.locked else ""), h.snippet])
            it.setData(0, Qt.UserRole, self.tree.topLevelItemCount())
            self.tree.addTopLevelItem(it)
        self.status.setText(f"{len(self.hits)} match(es)" if self.hits else "No matches")

    def _open(self, item) -> None:
        i = item.data(0, Qt.UserRole)
        if i is not None and 0 <= i < len(self.hits):
            h = self.hits[i]
            self.navigate.emit(h.section_id, h.block_id, h.matched)

    def replace_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        h = self.hits[item.data(0, Qt.UserRole)]
        if h.locked:
            self.status.setText("That block is locked. Unlock it in Block properties first.")
            return
        q, r, o = self.find.text(), self.repl.text(), self.options()
        ok = self.state.edit("Replace", lambda p: replace_one(p, h, q, r, o))
        self.status.setText("Replaced 1 match" if ok else "Could not replace (text changed?)")
        self.replaced.emit()
        self.run_search()

    def replace_everything(self) -> None:
        q = self.find.text()
        if not q:
            return
        self.state.flush()
        n = len(search_book(self.state.project, q, self.options()))
        if not n:
            self.status.setText("No matches")
            return
        scope = "the current chapter" if self.scope.currentData() else "the whole book"
        if QMessageBox.question(self, "Replace all", f"Replace {n} match(es) of “{q}” with "
                                f"“{self.repl.text()}” in {scope}?\n\nLocked blocks are skipped. "
                                "You can undo with Ctrl+Z.") != QMessageBox.Yes:
            return
        r, o = self.repl.text(), self.options()
        res = self.state.edit("Replace all", lambda p: replace_in_book(p, q, r, o))
        msg = f"Replaced {res.replaced} match(es)"
        if res.skipped_locked:
            msg += f"; {res.skipped_locked} in locked blocks were left unchanged"
        self.status.setText(msg)
        self.replaced.emit()
        self.run_search()
