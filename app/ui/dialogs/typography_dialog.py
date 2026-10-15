"""Typography cleanup dialog: counts first, then one undoable step."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QMessageBox, QVBoxLayout)

from ...application_state import AppState
from ...services.typography_service import QUOTE_STYLES, CleanupOptions, cleanup_book
from .. import theme


class TypographyDialog(QDialog):
    applied = Signal()

    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Typography cleanup")
        self.resize(480, 360)
        lay = QVBoxLayout(self)
        intro = QLabel("Fixes straight quotes, dashes, ellipses and spacing across the whole book. "
                       "Formatting is kept, code blocks and locked blocks are not touched. "
                       "You can undo it with Ctrl+Z.")
        intro.setWordWrap(True)
        theme.set_muted(intro)
        lay.addWidget(intro)
        form = QFormLayout()
        self.quotes = QComboBox()
        self.quotes.addItem("Leave quotation marks alone", None)
        for k, label in QUOTE_STYLES.items():
            self.quotes.addItem(label, k)
        lang = (state.project.metadata.language or "en")[:2].lower()
        self.quotes.setCurrentIndex(max(self.quotes.findData(lang if lang in QUOTE_STYLES else "en"), 0))
        self.apos = QCheckBox("Typographic apostrophes (n’am)")
        self.dashes = QCheckBox("Dashes: \" - \" and \"--\" become —; dialogue dashes at line starts")
        self.ellipsis = QCheckBox("Three dots become an ellipsis …")
        self.spaces = QCheckBox("Spacing: double spaces, line-end spaces, space before , . ; : ! ?")
        self.poetry = QCheckBox("Include poems")
        for w in (self.apos, self.dashes, self.ellipsis, self.spaces, self.poetry):
            w.setChecked(True)
            w.toggled.connect(self._count)
        self.quotes.currentIndexChanged.connect(self._count)
        form.addRow("Quotation marks", self.quotes)
        for w in (self.apos, self.dashes, self.ellipsis, self.spaces, self.poetry):
            form.addRow("", w)
        lay.addLayout(form)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        lay.addWidget(self.result)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.apply_btn = bb.addButton("Apply to book", QDialogButtonBox.AcceptRole)
        theme.accent_button(self.apply_btn)
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._count()

    def options(self) -> CleanupOptions:
        return CleanupOptions(quotes=self.quotes.currentData(), apostrophes=self.apos.isChecked(),
                              dashes=self.dashes.isChecked(), ellipsis=self.ellipsis.isChecked(),
                              spaces=self.spaces.isChecked(), include_poetry=self.poetry.isChecked())

    def _count(self) -> None:
        self.state.flush()
        rep = cleanup_book(self.state.project, self.options(), apply=False)
        self.result.setText(f"Would change: {rep.text()} in {rep.blocks_changed} block(s)."
                            + (f" {rep.skipped_locked} locked block(s) skipped." if rep.skipped_locked else ""))
        self.apply_btn.setEnabled(rep.total > 0)

    def _apply(self) -> None:
        o = self.options()
        rep = self.state.edit("Typography cleanup", lambda p: cleanup_book(p, o))
        self.applied.emit()
        QMessageBox.information(self, "Typography cleanup", f"Done: {rep.text()}.")
        self.accept()
