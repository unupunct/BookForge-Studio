"""Application-wide state: the open project, dirty tracking, undo, autosave, layout."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QUndoStack

from .commands import SnapshotCommand
from .domain.book import BookProject
from .domain.sections import Section
from .layout.model import LayoutResult
from .persistence.project_archive import (load_project, recover_from_backup, save_project)
from .services.autosave_service import AutosaveService, RecoveryCandidate
from .services.project_service import NewBookSpec, SettingsStore, create_project
from .services.template_service import TemplateService
from .workers.layout_worker import LayoutController


class AppState(QObject):
    project_changed = Signal()     # a different project is now open
    structure_changed = Signal()   # sections added/removed/moved/renamed
    section_changed = Signal(str)  # one section's metadata changed
    content_changed = Signal()     # block content edited
    settings_changed = Signal()    # layout/typography/metadata changed
    dirty_changed = Signal(bool)
    path_changed = Signal()
    layout_ready = Signal(object)
    layout_busy = Signal(bool)
    message = Signal(str)
    restored = Signal()            # undo/redo replaced the model objects

    def __init__(self, autosave: AutosaveService | None = None,
                 settings: SettingsStore | None = None,
                 templates: TemplateService | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.settings_store = settings or SettingsStore()
        self.autosave = autosave or AutosaveService()
        self.templates = templates or TemplateService()
        self.project: BookProject = BookProject()
        self.path: Path | None = None
        self._dirty = False
        self.layout: LayoutResult | None = None
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._undo_index_changed)
        self._flush_hooks: list[Callable[[], None]] = []

        self.layout_controller = LayoutController(parent=self)
        self.layout_controller.bind(self._snapshot)
        self.layout_controller.layout_ready.connect(self._on_layout)
        self.layout_controller.busy_changed.connect(self.layout_busy)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave_tick)
        self.apply_autosave_interval()

    # ------------------------------------------------------------ helpers
    def _snapshot(self) -> BookProject:
        self.flush()
        return self.project.snapshot()

    def add_flush_hook(self, fn: Callable[[], None]) -> None:
        self._flush_hooks.append(fn)

    def flush(self) -> None:
        """Commit pending editor text into the model."""
        for fn in self._flush_hooks:
            fn()

    def _undo_index_changed(self, _index: int) -> None:
        try:
            self.mark_dirty()
        except RuntimeError:  # Qt objects already torn down at interpreter shutdown
            pass

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self, dirty: bool = True) -> None:
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)

    def apply_autosave_interval(self) -> None:
        secs = max(int(self.settings_store.data.autosave_seconds), 0)
        self._autosave_timer.stop()
        if secs:
            self._autosave_timer.start(secs * 1000)

    def _autosave_tick(self) -> None:
        if self._dirty:
            self.flush()
            self.autosave.request(self.project, self.path)

    # ----------------------------------------------------------- project IO
    def _install(self, project: BookProject, path: Path | None, dirty: bool) -> None:
        self.project = project
        self.path = path
        self.layout = None
        self.undo_stack.clear()
        self.layout_controller.engine.clear_cache()
        self.mark_dirty(dirty)
        self.project_changed.emit()
        self.path_changed.emit()
        self.request_layout(immediate=True)

    def new_project(self, spec: NewBookSpec) -> None:
        self._install(create_project(spec, self.templates), None, True)

    def open_project(self, path: Path) -> None:
        proj = load_project(path)
        self._install(proj, Path(path), False)
        self.settings_store.add_recent(Path(path))

    def open_recovered(self, cand: RecoveryCandidate) -> None:
        proj = self.autosave.load(cand)
        orig = Path(cand.original_path) if cand.original_path else None
        self._install(proj, orig, True)

    def recover_backup(self) -> None:
        if self.path is None:
            raise ValueError("The project has not been saved yet")
        proj = recover_from_backup(self.path)
        self._install(proj, self.path, True)

    def save(self, path: Path | None = None) -> Path:
        target = Path(path) if path else self.path
        if target is None:
            raise ValueError("No path: use Save As")
        self.flush()
        if target.suffix.lower() != ".bookforge":
            target = target.with_suffix(".bookforge")
        save_project(self.project, target)
        self.path = target
        self.mark_dirty(False)
        self.autosave.discard(self.project.id)
        self.settings_store.add_recent(target)
        self.path_changed.emit()
        return target

    def duplicate_to(self, path: Path) -> Path:
        """Save a copy under a new name without switching the open project to it."""
        self.flush()
        target = Path(path).with_suffix(".bookforge")
        copy = self.project.snapshot()
        copy.sources = dict(self.project.sources)
        from .domain.content_blocks import new_id
        copy.id = new_id()
        save_project(copy, target)
        return target

    # ----------------------------------------------------------- layout
    def request_layout(self, immediate: bool = False) -> None:
        self.layout_controller.request(immediate)

    def _on_layout(self, result: LayoutResult, generation: int) -> None:
        self.layout = result
        self.layout_ready.emit(result)

    # ------------------------------------------------------------ editing
    def edit(self, label: str, fn: Callable[[BookProject], Any], *, kind: str = "structure",
             merge_key: str | None = None) -> Any:
        """Apply `fn` to the project as one undoable step.

        kind: "structure" (sections + content) | "settings" (settings, styles, metadata).
        """
        self.flush()
        before = self._capture()
        result = fn(self.project)
        after = self._capture()
        cmd = SnapshotCommand(label, before, after, self._restore)
        cmd.mergeable_key = merge_key
        self.undo_stack.push(cmd)
        if kind == "structure":
            self.structure_changed.emit()
        self.settings_changed.emit()
        self.request_layout()
        return result

    def _capture(self) -> dict[str, Any]:
        p = self.project
        return {"sections": p.structure_snapshot(), "metadata": p.metadata.to_dict(),
                "settings": p.settings.to_dict(),
                "styles": {k: v.to_dict() for k, v in p.styles.items()}}

    def _restore(self, snap: dict[str, Any]) -> None:
        from .domain.layouts import BookSettings
        from .domain.metadata import BookMetadata
        from .domain.styles import StyleDefinition
        p = self.project
        p.restore_structure(snap["sections"])
        p.metadata = BookMetadata.from_dict(snap["metadata"])
        p.settings = BookSettings.from_dict(snap["settings"])
        p.styles = {k: StyleDefinition.from_dict({**v, "name": k}) for k, v in snap["styles"].items()}
        self.structure_changed.emit()
        self.settings_changed.emit()
        self.restored.emit()
        self.request_layout()

    def content_edited(self) -> None:
        """Called by editors after they synchronised text into the model."""
        self.mark_dirty()
        self.content_changed.emit()
        self.request_layout()

    # --------------------------------------------------------- structure ops
    def add_section(self, section: Section, parent_id: str | None = None,
                    index: int | None = None) -> Section:
        return self.edit("Add " + (section.title or section.kind),
                         lambda p: p.add_section(section, parent_id, index))

    def remove_section(self, section_id: str) -> None:
        self.edit("Remove section", lambda p: p.remove_section(section_id))

    def duplicate_section(self, section_id: str) -> Section:
        return self.edit("Duplicate section", lambda p: p.duplicate_section(section_id))

    def move_section(self, section_id: str, delta: int) -> bool:
        ok = self.edit("Move section", lambda p: p.move_up_down(section_id, delta))
        return bool(ok)

    def rename_section(self, section_id: str, title: str) -> None:
        def fn(p: BookProject) -> None:
            s = p.find_section(section_id)
            if s:
                s.title = title
        self.edit("Rename section", fn, merge_key=f"rename:{section_id}")

    def set_section_attr(self, section_id: str, **attrs: Any) -> None:
        def fn(p: BookProject) -> None:
            s = p.find_section(section_id)
            if s:
                for k, v in attrs.items():
                    setattr(s, k, v)
        self.edit("Change section", fn, merge_key=f"sec:{section_id}:{','.join(sorted(attrs))}")

    def reorder_from_tree(self, structure: list[tuple[str, list]]) -> None:
        """Apply a drag-and-drop result: nested [(id, children)] describing the new order."""
        def fn(p: BookProject) -> None:
            by_id = {s.id: s for s in p.walk()}

            def build(nodes) -> list[Section]:
                out = []
                for sid, kids in nodes:
                    s = by_id[sid]
                    s.children = build(kids)
                    out.append(s)
                return out
            p.sections = build(structure)
        self.edit("Reorder sections", fn)
