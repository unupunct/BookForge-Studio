"""Template library: preview, duplicate, import, export, reset, save-from-book."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from ...application_state import AppState
from ...layout.pagination import LayoutEngine
from ...services.template_service import (TemplateError, apply_template, sample_book,
                                          template_from_book)
from .. import theme
from ..preview.page_renderer import render_page


class TemplateDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.svc = state.templates
        self.setWindowTitle("Template library")
        self.resize(760, 560)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setAccessibleName("Templates")
        left.addWidget(self.list, 1)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        theme.set_muted(self.desc)
        left.addWidget(self.desc)
        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.setMinimumSize(300, 420)
        self.preview.setAccessibleName("Template preview")
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        btns = QVBoxLayout()
        self.apply_btn = QPushButton("Apply to this book")
        theme.accent_button(self.apply_btn)
        self.dup_btn = QPushButton("Duplicate…")
        self.save_btn = QPushButton("Save book setup as template…")
        self.imp_btn = QPushButton("Import…")
        self.exp_btn = QPushButton("Export…")
        self.reset_btn = QPushButton("Reset to built-in")
        self.del_btn = QPushButton("Delete")
        for b in (self.apply_btn, self.dup_btn, self.save_btn, self.imp_btn, self.exp_btn,
                  self.reset_btn, self.del_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        left.addLayout(btns)
        lay.addLayout(left, 1)
        lay.addLayout(right, 1)
        self.list.currentItemChanged.connect(self._show)
        self.apply_btn.clicked.connect(self._apply)
        self.dup_btn.clicked.connect(self._duplicate)
        self.save_btn.clicked.connect(self._save_from_book)
        self.imp_btn.clicked.connect(self._import)
        self.exp_btn.clicked.connect(self._export)
        self.reset_btn.clicked.connect(self._reset)
        self.del_btn.clicked.connect(self._delete)
        self.reload()

    def reload(self, select: str | None = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for t in self.svc.list_templates():
            it = QListWidgetItem(t["name"] + ("" if t.get("builtin") else "  • yours"))
            it.setData(Qt.UserRole, t["key"])
            self.list.addItem(it)
        self.list.blockSignals(False)
        want = select or self.state.project.settings.template
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == want:
                self.list.setCurrentRow(i)
                return
        self.list.setCurrentRow(0)

    def _key(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _show(self, *_):
        key = self._key()
        if not key:
            return
        t = self.svc.get(key)
        s = t["settings"]
        self.desc.setText(f"{t.get('description', '')}\n{s.get('width_mm', '?')} × {s.get('height_mm', '?')} mm"
                          f"  •  {s.get('body_font', '')} {s.get('body_size', '')} pt")
        builtin_override = (self.svc.builtin_dir / f"{key}.json").exists()
        user_file = (self.svc.user_dir / f"{key}.json").exists()
        self.reset_btn.setEnabled(builtin_override and user_file)
        self.del_btn.setEnabled(user_file and not builtin_override)
        try:
            book = sample_book(t)
            res = LayoutEngine().build(book)
            page = res.pages[0]
            scale = 400.0 / page.height
            img = render_page(page, book.assets, scale)
            self.preview.setPixmap(QPixmap.fromImage(img))
        except Exception as e:  # a broken template must not break the dialog
            self.preview.setText(f"Preview unavailable:\n{e}")

    def _apply(self) -> None:
        key = self._key()
        if not key:
            return
        tpl = self.svc.get(key)
        if QMessageBox.question(self, "Apply template", f"Apply '{tpl['name']}'? Customised styles are kept. "
                                "You can undo with Ctrl+Z.") == QMessageBox.Yes:
            self.state.edit("Apply template", lambda p: apply_template(p, tpl), kind="settings")
            self.accept()

    def _duplicate(self) -> None:
        key = self._key()
        if not key:
            return
        name, ok = QInputDialog.getText(self, "Duplicate template", "Name for the copy:")
        if ok and name.strip():
            t = self.svc.duplicate(key, name.strip())
            self.reload(t["key"])

    def _save_from_book(self) -> None:
        name, ok = QInputDialog.getText(self, "Save template", "Template name:",
                                        text=self.state.project.metadata.title)
        if ok and name.strip():
            key = self.svc._slug(name)
            existing = {t["key"] for t in self.svc.list_templates()}
            n = 2
            base = key
            while key in existing:
                key = f"{base}_{n}"
                n += 1
            self.svc.save_user(template_from_book(self.state.project, name.strip(), key))
            self.reload(key)

    def _import(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Import template", "", "Template (*.json)")
        if p:
            try:
                t = self.svc.import_template(p)
                self.reload(t["key"])
            except TemplateError as e:
                QMessageBox.warning(self, "Import template", str(e))

    def _export(self) -> None:
        key = self._key()
        if key:
            p, _ = QFileDialog.getSaveFileName(self, "Export template", f"{key}.json", "Template (*.json)")
            if p:
                self.svc.export_template(key, p)

    def _reset(self) -> None:
        key = self._key()
        if key and QMessageBox.question(self, "Reset template", "Discard your changes to this built-in "
                                        "template?") == QMessageBox.Yes:
            self.svc.reset(key)
            self.reload(key)

    def _delete(self) -> None:
        key = self._key()
        if key and QMessageBox.question(self, "Delete template", "Delete this template?") == QMessageBox.Yes:
            self.svc.delete_user(key)
            self.reload()
