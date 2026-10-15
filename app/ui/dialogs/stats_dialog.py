"""Book statistics dialog."""
from __future__ import annotations

from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ...application_state import AppState
from ...services.stats_service import compute_stats
from .. import theme


class StatsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Book statistics")
        self.resize(520, 600)
        state.flush()
        self.stats = compute_stats(state.project, state.layout)
        lay = QVBoxLayout(self)
        title = QLabel(state.project.metadata.title)
        theme.set_heading(title)
        lay.addWidget(title)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Measure", "Value"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAccessibleName("Statistics")
        for k, v in self.stats.rows():
            self._row(k, v)
        lay.addWidget(self.table, 2)
        if self.stats.chapter_stats:
            lay.addWidget(QLabel("Longest sections"))
            self.longest = QTableWidget(0, 3)
            self.longest.setHorizontalHeaderLabels(["Section", "Words", "Pages"])
            self.longest.verticalHeader().hide()
            self.longest.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.longest.setEditTriggers(QTableWidget.NoEditTriggers)
            for c in self.stats.chapter_stats[:6]:
                r = self.longest.rowCount()
                self.longest.insertRow(r)
                for i, v in enumerate((c.title, f"{c.words:,}", "" if c.pages is None else str(c.pages))):
                    self.longest.setItem(r, i, QTableWidgetItem(v))
            lay.addWidget(self.longest, 1)
        copy = QPushButton("Copy as text")
        copy.clicked.connect(self.copy_text)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.addButton(copy, QDialogButtonBox.ActionRole)
        lay.addWidget(bb)

    def _row(self, k: str, v: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(k))
        self.table.setItem(r, 1, QTableWidgetItem(v))

    def as_text(self) -> str:
        lines = [f"{k}: {v}" for k, v in self.stats.rows()]
        lines.append("")
        lines.extend(f"{c.title}: {c.words:,} words" + (f", {c.pages} pages" if c.pages else "")
                     for c in self.stats.chapter_stats[:6])
        return "\n".join(lines)

    def copy_text(self) -> None:
        QApplication.clipboard().setText(self.as_text())
