"""The BookForge Studio main window."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QProgressBar, QPushButton, QTabWidget,
                               QToolBar, QWidget)

from . import __version__
from .application_state import AppState
from .layout.pagination import LayoutEngine
from .persistence.project_archive import ProjectFormatError, backup_path
from .services.import_service import commit_import
from .services.validation_service import ValidationReport, validate_book
from .ui import theme
from .ui.book_navigator import BookNavigator
from .ui.dialogs.export_dialog import ExportDialog
from .ui.dialogs.import_dialog import ImportDialog
from .ui.dialogs.misc_dialogs import CoverDialog, SettingsDialog, ValidationDialog
from .ui.dialogs.search_dialog import SearchDialog
from .ui.dialogs.template_dialog import TemplateDialog
from .ui.dialogs.wizard import NewBookWizard
from .ui.editor.chapter_editor import ChapterEditor
from .ui.preview.preview_panel import PreviewPanel
from .ui.properties_panel import PropertiesPanel
from .workers.task import run_task

SHORTCUTS = [
    ("Ctrl+N", "New book"), ("Ctrl+O", "Open project"), ("Ctrl+S", "Save"),
    ("Ctrl+Shift+S", "Save as"), ("Ctrl+I", "Import manuscript"), ("Ctrl+E", "Export"),
    ("Ctrl+Z / Ctrl+Y", "Undo / Redo"), ("Ctrl+B / I / U", "Bold / Italic / Underline"),
    ("Ctrl+K", "Hyperlink"), ("Ctrl+F", "Find in chapter"), ("F3 / Shift+F3", "Find next / previous"),
    ("Ctrl+Shift+F", "Search the whole book"), ("F5", "Toggle page preview"),
    ("F7", "Validate book"), ("F2", "Rename section"), ("Alt+Up / Alt+Down", "Move section"),
    ("Page Up / Down", "Previous / next page in preview"), ("Ctrl+wheel", "Zoom preview"),
    ("Ctrl+,", "Settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, state: AppState | None = None):
        super().__init__()
        self.state = state or AppState()
        self.setWindowTitle("BookForge Studio")
        self.resize(1480, 900)
        self.search_dialog: SearchDialog | None = None
        self.validation_dialog: ValidationDialog | None = None
        self.last_report: ValidationReport | None = None
        self._validating = False
        self._discarded = False

        self.navigator = BookNavigator(self.state)
        self.editor = ChapterEditor(self.state)
        self.preview = PreviewPanel(self.state)
        self.properties = PropertiesPanel(self.state)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.editor, "Write")
        self.tabs.addTab(self.preview, "Preview")
        self.tabs.setDocumentMode(True)
        self.setCentralWidget(self.tabs)
        self.properties.block_tab.bind(self.editor)

        self._dock("Book navigator", self.navigator, Qt.LeftDockWidgetArea, 280)
        self._dock("Properties", self.properties, Qt.RightDockWidgetArea, 340)
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._wire()
        self._update_all()
        self.setAcceptDrops(True)
        QTimer.singleShot(0, self._restore_geometry)
        self.navigator.rebuild()

    # ------------------------------------------------------------------ build
    def _dock(self, title: str, widget: QWidget, area, width: int) -> QDockWidget:
        d = QDockWidget(title, self)
        d.setObjectName(title)
        d.setWidget(widget)
        d.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        d.setMinimumWidth(220)
        self.addDockWidget(area, d)
        self.resizeDocks([d], [width], Qt.Horizontal)
        return d

    def _action(self, text: str, slot, shortcut=None, tip: str = "") -> QAction:
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.setToolTip(tip or text.replace("&", "").rstrip("…"))
        a.setStatusTip(tip or text.replace("&", ""))
        a.triggered.connect(slot)
        return a

    def _build_actions(self) -> None:
        A = self._action
        self.act_new = A("&New book…", self.new_project, QKeySequence.New, "Create a new book with the wizard")
        self.act_open = A("&Open…", self.open_project, QKeySequence.Open, "Open a .bookforge project")
        self.act_save = A("&Save", self.save, QKeySequence.Save, "Save the project")
        self.act_save_as = A("Save &as…", self.save_as, QKeySequence.SaveAs, "Save under a new name")
        self.act_duplicate = A("&Duplicate project…", self.duplicate_project, None,
                               "Save a copy and keep working on this one")
        self.act_recover = A("Recover from &backup", self.recover_backup, None,
                             "Restore the previous saved version of this project")
        self.act_import = A("&Import manuscript…", self.import_manuscript, "Ctrl+I",
                            "Import DOCX, TXT, Markdown, HTML or PDF text")
        self.act_export = A("&Export…", self.export_book, "Ctrl+E", "Export PDF, DOCX, HTML or Markdown")
        self.act_quit = A("E&xit", self.close, "Ctrl+Q")
        self.act_undo = A("&Undo", self.undo, QKeySequence.Undo, "Undo the last change")
        self.act_redo = A("&Redo", self.redo, QKeySequence("Ctrl+Y"), "Redo")
        self.act_redo_alt = QAction(self)
        self.act_redo_alt.setShortcut(QKeySequence.Redo)
        self.act_redo_alt.triggered.connect(self.redo)
        self.addAction(self.act_redo_alt)
        self.act_find_book = A("Search the &book…", self.show_search, "Ctrl+Shift+F",
                               "Find and replace across all chapters")
        self.act_preview = A("&Preview", self.toggle_preview, "F5", "Show or hide the page preview")
        self.act_validate = A("&Validate book", self.validate, "F7", "Check the book for problems")
        self.act_relink = A("&Relink missing images…", self.relink_missing, None,
                            "Point missing images at replacement files")
        self.act_cover = A("&Cover design…", self.cover_design, None, "Design the front and back covers")
        self.act_templates = A("&Templates…", self.templates, None, "Browse and apply templates")
        self.act_settings = A("&Settings…", self.settings, "Ctrl+,", "Application settings")
        self.act_shortcuts = A("&Keyboard shortcuts", self.show_shortcuts)
        self.act_about = A("&About BookForge Studio", self.about)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        f = mb.addMenu("&File")
        f.addAction(self.act_new)
        f.addAction(self.act_open)
        self.recent_menu = f.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        f.addSeparator()
        for a in (self.act_save, self.act_save_as, self.act_duplicate, self.act_recover):
            f.addAction(a)
        f.addSeparator()
        f.addAction(self.act_import)
        f.addAction(self.act_export)
        f.addSeparator()
        f.addAction(self.act_quit)
        e = mb.addMenu("&Edit")
        e.addAction(self.act_undo)
        e.addAction(self.act_redo)
        e.addSeparator()
        e.addAction(self._action("&Find in chapter", self.editor.show_find, None,
                                 "Find and replace in the open chapter"))
        e.addAction(self.act_find_book)
        v = mb.addMenu("&View")
        v.addAction(self.act_preview)
        for d in self.findChildren(QDockWidget):
            v.addAction(d.toggleViewAction())
        b = mb.addMenu("&Book")
        b.addAction(self.act_validate)
        b.addAction(self.act_cover)
        b.addAction(self.act_relink)
        b.addAction(self.act_templates)
        t = mb.addMenu("&Tools")
        t.addAction(self.act_settings)
        h = mb.addMenu("&Help")
        h.addAction(self.act_shortcuts)
        h.addAction(self.act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        for a in (self.act_new, self.act_open, self.act_save):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_import, self.act_export):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_undo, self.act_redo):
            tb.addAction(a)
        tb.addSeparator()
        for a in (self.act_preview, self.act_validate, self.act_settings):
            tb.addAction(a)
        self.addToolBar(Qt.TopToolBarArea, tb)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_project = QLabel("")
        self.lbl_chapter = QLabel("")
        self.lbl_words = QLabel("")
        self.lbl_pages = QLabel("")
        self.lbl_dirty = QLabel("")
        self.btn_valid = QPushButton("Not validated")
        self.btn_valid.setFlat(True)
        self.btn_valid.setToolTip("Click to validate the book (F7)")
        self.btn_valid.clicked.connect(self.validate)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(120)
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.progress.setToolTip("Background job in progress")
        for w in (self.lbl_project, self.lbl_chapter, self.lbl_words, self.lbl_pages):
            sb.addWidget(w)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.btn_valid)
        sb.addPermanentWidget(self.lbl_dirty)

    def _wire(self) -> None:
        s = self.state
        self.navigator.section_selected.connect(self._section_selected)
        s.project_changed.connect(self._project_changed)
        s.structure_changed.connect(self._update_all)
        s.settings_changed.connect(self._update_all)
        s.content_changed.connect(self._update_counts)
        s.dirty_changed.connect(lambda _: self._update_title())
        s.path_changed.connect(self._update_title)
        s.layout_ready.connect(lambda _: self._update_counts())
        s.layout_busy.connect(self.progress.setVisible)
        s.restored.connect(self._restored)
        s.message.connect(lambda m: self.statusBar().showMessage(m, 5000))
        self.editor.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
        self.editor.edit.cursorPositionChanged.connect(self.properties.block_tab.refresh)
        self.preview.block_requested.connect(self._open_block)
        self.properties.templates_requested.connect(self.templates)
        s.layout_controller.layout_failed.connect(
            lambda m: self.statusBar().showMessage("Layout problem: " + m, 8000))

    # ----------------------------------------------------------------- updates
    def _project_changed(self) -> None:
        self.editor.load_section(None)
        self.navigator.rebuild()
        self.properties.section_tab.load(self.navigator.current_id())
        self.properties.book_tab.load()
        self.last_report = None
        self.btn_valid.setText("Not validated")
        self._update_all()

    def _restored(self) -> None:
        cur = self.navigator.current_id()
        self.navigator.rebuild()
        if cur and self.state.project.find_section(cur):
            self.editor.reload_if_stale()
        self._update_all()

    def _section_selected(self, section_id: str) -> None:
        self.editor.load_section(section_id)
        self.properties.section_tab.load(section_id)
        self.properties.block_tab.refresh()
        if self.state.layout:
            self.preview.show_section(section_id)
        self._update_all()

    def _update_all(self) -> None:
        self._update_title()
        self._update_counts()
        sid = self.navigator.current_id()
        if sid:
            self.properties.section_tab.load(sid)

    def _update_title(self) -> None:
        p = self.state
        name = p.path.name if p.path else "Untitled"
        self.setWindowTitle(f"{'● ' if p.dirty else ''}{p.project.metadata.title} — {name} — BookForge Studio")
        self.lbl_project.setText(f"{p.project.metadata.title}")
        self.lbl_dirty.setText("● Unsaved changes" if p.dirty else "Saved")
        self.lbl_dirty.setStyleSheet(f"color: {theme.WARNING if p.dirty else theme.OK};")

    def _update_counts(self) -> None:
        p = self.state.project
        sec = p.find_section(self.navigator.current_id()) if self.navigator.current_id() else None
        self.lbl_chapter.setText(f"Chapter: {sec.title or '—'}" if sec else "Chapter: —")
        words = p.word_count()
        chars = p.char_count()
        cw = f"{p.word_count(sec):,}" if sec else "0"
        self.lbl_words.setText(f"{cw} words here • {words:,} words, {chars:,} characters in book")
        if self.state.layout:
            self.lbl_pages.setText(f"{self.state.layout.page_count} pages")
        else:
            self.lbl_pages.setText(f"~{max(words // 280, 1)} pages (estimate)")

    # ---------------------------------------------------------------- helpers
    def show_error(self, title: str, message: str, details: str = "") -> None:
        box = QMessageBox(QMessageBox.Critical, title, message, QMessageBox.Ok, self)
        if details:
            box.setDetailedText(details)
        box.exec()

    def confirm_discard(self) -> bool:
        """Returns True if it is safe to replace the open project."""
        if not self.state.dirty:
            return True
        self.state.flush()
        r = QMessageBox.question(self, "Unsaved changes",
                                 "Save changes to this book before continuing?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                                 QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        if r == QMessageBox.Discard:
            self._discarded = True
            return True
        return False

    # ------------------------------------------------------------------ actions
    def new_project(self) -> None:
        if not self.confirm_discard():
            return
        wiz = NewBookWizard(self, self.state.templates)
        if wiz.exec():
            self.state.new_project(wiz.spec())
            self.tabs.setCurrentWidget(self.editor)

    def open_project(self, path: str | None = None) -> None:
        if not self.confirm_discard():
            return
        if not path:
            start = self.state.settings_store.data.last_open_dir
            path, _ = QFileDialog.getOpenFileName(self, "Open project", start, "BookForge project (*.bookforge)")
        if not path:
            return
        self._open_path(Path(path))

    def _open_path(self, path: Path) -> bool:
        try:
            self.state.open_project(path)
        except (ProjectFormatError, OSError) as e:
            bak = backup_path(path)
            msg = f"The project could not be opened.\n\n{e}"
            if bak.exists():
                r = QMessageBox.question(self, "Open project", msg + "\n\nA backup copy of the last "
                                         "saved version exists. Open the backup instead?")
                if r == QMessageBox.Yes:
                    try:
                        self._open_backup(path)
                        return True
                    except (ProjectFormatError, OSError) as e2:
                        self.show_error("Open backup", str(e2))
                return False
            self.show_error("Open project", msg)
            return False
        self.state.settings_store.data.last_open_dir = str(path.parent)
        self.state.settings_store.save()
        return True

    def _open_backup(self, path: Path) -> None:
        from .persistence.project_archive import recover_from_backup
        proj = recover_from_backup(path)
        self.state._install(proj, path, True)

    def _fill_recent(self) -> None:
        self.recent_menu.clear()
        recent = self.state.settings_store.existing_recent()
        if not recent:
            self.recent_menu.addAction("(none)").setEnabled(False)
        for r in recent:
            self.recent_menu.addAction(Path(r).name, lambda r=r: self.open_project(r)).setToolTip(r)

    def save(self) -> bool:
        if self.state.path is None:
            return self.save_as()
        try:
            self.state.save()
        except (OSError, ValueError) as e:
            self.show_error("Save", f"The project could not be saved.\n\n{e}\n\nNothing was overwritten.")
            return False
        self.statusBar().showMessage(f"Saved {self.state.path.name}", 4000)
        return True

    def save_as(self) -> bool:
        start = str(self.state.path) if self.state.path else str(
            Path(self.state.settings_store.data.last_open_dir or Path.home()) /
            (self.state.project.metadata.title.strip() or "book"))
        p, _ = QFileDialog.getSaveFileName(self, "Save project as", start, "BookForge project (*.bookforge)")
        if not p:
            return False
        try:
            self.state.save(Path(p))
        except (OSError, ValueError) as e:
            self.show_error("Save as", f"The project could not be saved.\n\n{e}")
            return False
        self.statusBar().showMessage(f"Saved {self.state.path.name}", 4000)
        return True

    def duplicate_project(self) -> None:
        p, _ = QFileDialog.getSaveFileName(self, "Save a copy", "", "BookForge project (*.bookforge)")
        if p:
            try:
                target = self.state.duplicate_to(Path(p))
                self.statusBar().showMessage(f"Copy saved as {target.name}", 5000)
            except OSError as e:
                self.show_error("Duplicate project", str(e))

    def recover_backup(self) -> None:
        if self.state.path is None or not backup_path(self.state.path).exists():
            QMessageBox.information(self, "Recover", "This project has no backup copy yet. A backup is "
                                    "created each time you save over an existing file.")
            return
        if QMessageBox.question(self, "Recover from backup", "Replace the open book with the backup copy "
                                "(the version before your last save)?") != QMessageBox.Yes:
            return
        try:
            self._open_backup(self.state.path)
        except (ProjectFormatError, OSError) as e:
            self.show_error("Recover from backup", str(e))

    def import_manuscript(self, path: str | None = None) -> None:
        dlg = ImportDialog(self, self.state.settings_store.data.last_open_dir, path or "")
        if dlg.exec() and dlg.staged:
            staged, opts = dlg.staged, dlg.options
            self.state.flush()

            def apply(p):
                return commit_import(p, staged, opts)
            sections = self.state.edit("Import " + staged.source_name, apply)
            self.navigator.rebuild()
            if sections:
                self.navigator.select(sections[0].id)
            self.tabs.setCurrentWidget(self.editor)
            self.statusBar().showMessage(f"Imported {len(sections)} chapter(s) from {staged.source_name}", 6000)

    def export_book(self) -> None:
        self.state.flush()
        ExportDialog(self.state, self).exec()

    def undo(self) -> None:
        if self.editor.edit.hasFocus() and self.editor.edit.document().isUndoAvailable():
            self.editor.undo()
        else:
            self.state.flush()
            self.state.undo_stack.undo()

    def redo(self) -> None:
        if self.editor.edit.hasFocus() and self.editor.edit.document().isRedoAvailable():
            self.editor.redo()
        else:
            self.state.undo_stack.redo()

    def toggle_preview(self) -> None:
        if self.tabs.currentWidget() is self.preview:
            self.tabs.setCurrentWidget(self.editor)
        else:
            self.state.flush()
            self.state.request_layout(immediate=True)
            self.tabs.setCurrentWidget(self.preview)
            sid = self.navigator.current_id()
            if sid:
                self.preview.show_section(sid)

    def show_search(self) -> None:
        if self.search_dialog is None:
            self.search_dialog = SearchDialog(self.state, self)
            self.search_dialog.navigate.connect(self._navigate_hit)
            self.search_dialog.replaced.connect(self._after_replace)
        self.search_dialog.current_section_id = self.navigator.current_id()
        self.search_dialog.show()
        self.search_dialog.raise_()
        self.search_dialog.find.setFocus()

    def _after_replace(self) -> None:
        self.editor.reload_if_stale()
        self.state.request_layout()

    def _navigate_hit(self, section_id: str, block_id: str, text: str) -> None:
        self.navigator.select(section_id)
        self.tabs.setCurrentWidget(self.editor)
        self.editor.scroll_to_block(block_id, text)

    def _open_block(self, block_id: str) -> None:
        found = self.state.project.find_block(block_id)
        if found:
            self._navigate_hit(found[0].id, block_id, "")

    def validate(self) -> None:
        if self._validating:
            return
        self._validating = True
        self.state.flush()
        book = self.state.project.snapshot()
        profile = self.state.project.settings.export_profile
        self.btn_valid.setText("Validating…")
        self.progress.show()

        def work(ctx):
            layout = LayoutEngine().build(book, ctx.cancelled)
            return validate_book(book, layout, profile)
        run_task(work, self._validated, self._validation_failed)

    def _validated(self, report: ValidationReport) -> None:
        self._validating = False
        self.progress.hide()
        self.last_report = report
        e, w = len(report.errors), len(report.warnings)
        self.btn_valid.setText(f"✔ No issues" if not (e or w) else f"⚠ {e} errors, {w} warnings")
        self.btn_valid.setStyleSheet(f"color: {theme.ERROR if e else theme.WARNING if w else theme.OK};")
        if self.validation_dialog:
            self.validation_dialog.close()
        self.validation_dialog = ValidationDialog(report, self)
        self.validation_dialog.navigate.connect(self._navigate_issue)
        self.validation_dialog.show()

    def _validation_failed(self, message: str, exc) -> None:
        self._validating = False
        self.progress.hide()
        self.btn_valid.setText("Validation failed")
        self.show_error("Validate book", message)

    def _navigate_issue(self, issue) -> None:
        if issue.block_id:
            found = self.state.project.find_block(issue.block_id)
            if found:
                self.navigator.select(found[0].id)
                self.tabs.setCurrentWidget(self.preview if issue.page_index is not None else self.editor)
                if issue.page_index is not None:
                    self.preview.show_block(issue.block_id)
                else:
                    self.editor.scroll_to_block(issue.block_id)
                return
        if issue.section_id and self.state.project.find_section(issue.section_id):
            self.navigator.select(issue.section_id)
        if issue.page_index is not None:
            self.tabs.setCurrentWidget(self.preview)
            self.preview.show_page(issue.page_index)

    def relink_missing(self) -> int:
        """Ask for a replacement file for every image whose data is missing. Returns how many were fixed."""
        from .persistence.project_archive import relink_asset
        missing = [a for a in self.state.project.assets.values() if not a.data]
        if not missing:
            QMessageBox.information(self, "Relink images", "No images are missing.")
            return 0
        fixed = 0
        for a in missing:
            path, _ = QFileDialog.getOpenFileName(
                self, f"Find a replacement for “{a.filename}” (Cancel to skip)",
                str(Path(a.source_path).parent) if a.source_path else "", "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.tif *.tiff)")
            if not path:
                continue
            try:
                relink_asset(self.state.project, a.id, Path(path))
                fixed += 1
            except Exception as e:
                self.show_error("Relink image", f"That file could not be used:\n{e}")
        if fixed:
            self.state.mark_dirty()
            self.state.layout_controller.engine.clear_cache()
            self.state.request_layout()
            self.statusBar().showMessage(f"Relinked {fixed} image(s)", 5000)
        return fixed

    def cover_design(self) -> None:
        self.state.flush()
        CoverDialog(self.state, self).exec()

    def templates(self) -> None:
        TemplateDialog(self.state, self).exec()
        self.properties.book_tab.load()

    def settings(self) -> None:
        SettingsDialog(self.state, self).exec()

    def show_shortcuts(self) -> None:
        text = "\n".join(f"{k:<22}{v}" for k, v in SHORTCUTS)
        box = QMessageBox(QMessageBox.Information, "Keyboard shortcuts", "<pre>" + text + "</pre>",
                          QMessageBox.Ok, self)
        box.setTextFormat(Qt.RichText)
        box.exec()

    def about(self) -> None:
        QMessageBox.about(self, "About BookForge Studio",
                          f"<b>BookForge Studio {__version__}</b><br>Local-first book creation and "
                          "publishing.<br>Your manuscripts never leave this computer.")

    # -------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() == ".bookforge":
                self.open_project(str(p))
                return
            self.import_manuscript(str(p))
            return

    # ------------------------------------------------------------------ lifecycle
    @staticmethod
    def _window_settings() -> QSettings:
        # Stored beside the other per-user data (an INI file), never in the registry.
        from .services.app_paths import user_data_dir
        return QSettings(str(user_data_dir() / "window.ini"), QSettings.IniFormat)

    def _restore_geometry(self) -> None:
        try:
            s = self._window_settings()
            g, st = s.value("geometry"), s.value("state")
            if g:
                self.restoreGeometry(g)
            if st:
                self.restoreState(st)
        except Exception:
            pass

    def check_recovery(self) -> None:
        cands = self.state.autosave.candidates()
        for c in cands[:1]:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(c.saved_at))
            r = QMessageBox.question(
                self, "Recover unsaved work",
                f"BookForge Studio did not close normally. An autosaved copy of "
                f"“{c.title or 'Untitled'}” from {when} is available.\n\nRecover it now?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Discard, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                try:
                    self.state.open_recovered(c)
                except ProjectFormatError as e:
                    self.show_error("Recover", f"The autosave could not be read:\n{e}")
            elif r == QMessageBox.Discard:
                self.state.autosave.discard(c.project_id)

    def closeEvent(self, e: QCloseEvent) -> None:
        if not self.confirm_discard():
            e.ignore()
            return
        self.state.flush()
        self.state.autosave.wait_idle(3)
        if not self.state.dirty or self._discarded:
            self.state.autosave.discard(self.state.project.id)
        try:
            s = self._window_settings()
            s.setValue("geometry", self.saveGeometry())
            s.setValue("state", self.saveState())
        except Exception:
            pass
        e.accept()
