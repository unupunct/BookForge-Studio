"""Autosave and crash recovery.

The snapshot (a plain dict + bytes) is taken on the caller's thread; the slow
ZIP writing happens on a background thread so the UI never blocks.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..domain.book import BookProject
from ..persistence.project_archive import (ProjectFormatError, load_project, snapshot_for_save,
                                           write_archive)
from .app_paths import recovery_dir


@dataclass
class RecoveryCandidate:
    project_id: str
    recovery_path: Path
    original_path: str | None
    saved_at: float
    title: str


class AutosaveService:
    def __init__(self, directory: Path | None = None):
        self.dir = directory or recovery_dir()
        self._lock = threading.Lock()
        self._busy = False
        self._pending: tuple | None = None
        self.last_error: str | None = None

    def _paths(self, project_id: str) -> tuple[Path, Path]:
        return self.dir / f"{project_id}.bookforge", self.dir / f"{project_id}.json"

    def request(self, project: BookProject, original_path: Path | None) -> None:
        """Snapshot now, write in the background. Coalesces overlapping requests."""
        manifest, files = snapshot_for_save(project)
        job = (project.id, manifest, files, str(original_path) if original_path else None)
        with self._lock:
            if self._busy:
                self._pending = job
                return
            self._busy = True
        threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _run(self, job: tuple) -> None:
        while True:
            pid, manifest, files, original = job
            try:
                data_path, meta_path = self._paths(pid)
                write_archive(data_path, manifest, files, keep_backup=False)
                meta_path.write_text(json.dumps({
                    "project_id": pid, "original": original, "saved_at": time.time(),
                    "title": manifest["project"]["metadata"].get("title", "")}), encoding="utf-8")
                self.last_error = None
            except Exception as e:  # autosave must never crash the application
                self.last_error = str(e)
            with self._lock:
                if self._pending is None:
                    self._busy = False
                    return
                job, self._pending = self._pending, None

    def wait_idle(self, timeout: float = 10.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            with self._lock:
                if not self._busy:
                    return True
            time.sleep(0.02)
        return False

    def discard(self, project_id: str) -> None:
        for p in self._paths(project_id):
            p.unlink(missing_ok=True)

    def candidates(self) -> list[RecoveryCandidate]:
        """Recovery files newer than the saved project (or whose project no longer exists)."""
        out: list[RecoveryCandidate] = []
        for meta_path in self.dir.glob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                data_path = meta_path.with_suffix(".bookforge")
                if not data_path.exists():
                    continue
                original = meta.get("original")
                if original and Path(original).exists() and \
                        Path(original).stat().st_mtime >= float(meta["saved_at"]):
                    continue  # the user saved after the last autosave: nothing to recover
                out.append(RecoveryCandidate(meta["project_id"], data_path, original,
                                             float(meta["saved_at"]), meta.get("title", "")))
            except (OSError, ValueError, KeyError):
                continue
        return sorted(out, key=lambda c: c.saved_at, reverse=True)

    def load(self, candidate: RecoveryCandidate) -> BookProject:
        try:
            return load_project(candidate.recovery_path)
        except ProjectFormatError:
            raise
