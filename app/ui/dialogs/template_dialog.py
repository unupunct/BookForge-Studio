"""Template library: preview, duplicate, import, export, reset, save-from-book."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from ...application_state import AppState
from ...layout.model import Glyphs
from ...layout.pagination import LayoutEngine
from ...services.template_service import (TemplateError, apply_template, preview_book,
                                          template_from_book)
from .. import theme
from ..preview.page_renderer import render_page


class TemplateDialog(QDialog):
    def __init__(self, state: AppState, parent=None):
        super().__init__(parent)
        self.state = state
        self.svc = state.templates
        self.setWindowTitle("Template library")
        self.resize(1040, 600)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setAccessibleName("Templates")
        left.addWidget(self.list, 1)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        theme.set_muted(self.desc)
        left.addWidget(self.desc)
        self.pages = [QLabel(alignment=Qt.AlignCenter) for _ in range(3)]
        for lbl, name in zip(self.pages, ("Cover", "Opening page", "Next page")):
            lbl.setMinimumSize(190, 300)
            lbl.setAccessibleName(f"Template preview: {name}")
        self.preview = self.pages[1]  # shown text for errors
        self.use_mine = QCheckBox("Preview with the text of this book")
        self.use_mine.setChecked(True)
        self.use_mine.toggled.connect(self._show)
        right = QVBoxLayout()
        row = QHBoxLayout()
        for lbl in self.pages:
            row.addWidget(lbl, 1)
        right.addLayout(row, 1)
        right.addWidget(self.use_mine)
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
            self._render(t)
        except Exception as e:  # a broken template must not break the dialog
            for lbl in self.pages:
                lbl.clear()
            self.preview.setText(f"Preview unavailable:\n{e}")

    def _render(self, t: dict) -> None:
        """Cover plus the first two text pages, laid out exactly as the book would be."""
        source = self.state.project if self.use_mine.isChecked() else None
        book = preview_book(t, source)
        res = LayoutEngine().build(book)
        text_pages = [p for p in res.pages[1:] if any(isinstance(i, Glyphs) for i in p.items)]
        shown = [res.pages[0]] + text_pages[1:3]  # text_pages[0] is the title page; the chapter follows it
        for lbl, page in zip(self.pages, shown + [None] * 3):
            if page is None:
                lbl.clear()
                continue
            img = render_page(page, book.assets, 320.0 / page.height)
            lbl.setPixmap(QPixmap.fromImage(img))

    def _apply(self) -> None:
        key = self._key()
        if not key:
            return
        tpl = self.svc.get(key)
        if QMessageBox.question(self, "Apply template", f"Apply '{tpl['name']}'? Customised styles are kept, and so is a cover "
                                "you designed yourself. You can undo with Ctrl+Z.") == QMessageBox.Yes:
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
