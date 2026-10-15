"""Undo/redo commands for structural and settings edits.

Text edits are undone by the editor's own document history; everything else goes
through snapshot commands so that any operation (add, move, rename, template
application, style change...) can be undone safely.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtGui import QUndoCommand


class SnapshotCommand(QUndoCommand):
    def __init__(self, text: str, before: dict[str, Any], after: dict[str, Any],
                 restore: Callable[[dict[str, Any]], None]):
        super().__init__(text)
        self._before, self._after, self._restore = before, after, restore
        self._first = True
        self.mergeable_key: str | None = None

    def redo(self) -> None:
        if self._first:  # the change was already applied when the command was recorded
            self._first = False
            return
        self._restore(self._after)

    def undo(self) -> None:
        self._restore(self._before)

    # Consecutive edits of the same property (e.g. spinbox scrolling) collapse into one step.
    def id(self) -> int:
        return hash(self.mergeable_key) & 0x7FFFFFFF if self.mergeable_key else -1

    def mergeWith(self, other: QUndoCommand) -> bool:
        if isinstance(other, SnapshotCommand) and self.mergeable_key and \
                other.mergeable_key == self.mergeable_key:
            self._after = other._after
            return True
        return False
