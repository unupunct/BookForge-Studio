"""Settings, validation report and cover design dialogs."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from ...application_state import AppState
from ...domain.layouts import CoverDesign
from ...layout.model import Page
from ...layout.page_builder import cover_items
from ...layout.typography import LOGICAL_FAMILIES, fonts
from ...services.validation_service import ValidationReport
from .. import theme
from ..editor.block_dialogs import choose_and_add_image
from ..preview.page_renderer import render_page


class SettingsDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Settings")
        form = QFormLayout(self)
        d = state.settings_store.data
        self.autosave = QSpinBox(minimum=0, maximum=3600, suffix=" s", value=d.autosave_seconds)
        self.autosave.setToolTip("0 turns autosave off")
        self.scale = QDoubleSpinBox(minimum=0.8, maximum=2.0, singleStep=0.1, value=d.ui_scale)
        self.scale.setToolTip("Interface text scale. Takes effect after restarting.")
        form.addRow("Autosave interval", self.autosave)
        form.addRow("Interface scale (restart)", self.scale)
        info = QLabel("Fonts used for layout:\n" + ", ".join(fonts.installed_families()))
        info.setWordWrap(True)
        theme.set_muted(info)
        form.addRow(info)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _ok(self) -> None:
        d = self.state.settings_store.data
        d.autosave_seconds = self.autosave.value()
        d.ui_scale = self.scale.value()
        self.state.settings_store.save()
        self.state.apply_autosave_interval()
        self.accept()


class ValidationDialog(QDialog):
    navigate = Signal(object)  # ValidationIssue

    def __init__(self, report: ValidationReport, parent=None):
        super().__init__(parent)
        self.report = report
        self.setWindowTitle("Book validation")
        self.resize(640, 460)
        self.setModal(False)
        lay = QVBoxLayout(self)
        head = QLabel(("✔ No problems found." if not report.issues else report.summary()))
        theme.set_heading(head)
        lay.addWidget(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Severity", "Issue"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 90)
        self.tree.setAccessibleName("Validation issues")
        col = {"error": theme.ERROR, "warning": theme.WARNING, "info": theme.TEXT_MUTED}
        order = {"error": 0, "warning": 1, "info": 2}
        for n, i in enumerate(sorted(report.issues, key=lambda x: order.get(x.severity, 3))):
            it = QTreeWidgetItem([i.severity.upper(), i.message +
                                  (f"  (page {i.page_index + 1})" if i.page_index is not None else "")])
            it.setForeground(0, QBrush(QColor(col.get(i.severity, theme.TEXT))))
            it.setData(0, Qt.UserRole, i)
            self.tree.addTopLevelItem(it)
        self.tree.itemDoubleClicked.connect(lambda it, _: self.navigate.emit(it.data(0, Qt.UserRole)))
        lay.addWidget(self.tree, 1)
        hint = QLabel("Double-click an issue to jump to it.")
        theme.set_muted(hint)
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.close)
        lay.addWidget(bb)
