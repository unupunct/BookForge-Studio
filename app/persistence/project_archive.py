"""The `.bookforge` project package: a ZIP with a JSON manifest and assets."""
from __future__ import annotations

import json
import os
import posixpath
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from ..domain.book import SCHEMA_VERSION, Asset, BookProject
from .migrations import MigrationError, migrate, needs_migration

FORMAT_NAME = "bookforge"
MANIFEST = "manifest.json"
MAX_ARCHIVE_UNCOMPRESSED = 2 * 1024**3  # 2 GiB
MAX_MEMBER_SIZE = 512 * 1024**2
MAX_MEMBERS = 20000
MAX_SOURCE_SNAPSHOT = 50 * 1024**2
EXTENSION = ".bookforge"


class ProjectFormatError(Exception):
    """The file is not a valid or safe BookForge project."""


def _safe_member(name: str) -> bool:
    if not name or name.startswith(("/", "\\")) or "\\" in name or ":" in name:
        return False
    parts = posixpath.normpath(name).split("/")
    return ".." not in parts and posixpath.normpath(name) == name.rstrip("/")


def snapshot_for_save(project: BookProject) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Capture manifest + binary payload so zipping can happen off the UI thread."""
    manifest = {
        "format": FORMAT_NAME,
        "schema_version": SCHEMA_VERSION,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "app": "BookForge Studio 0.1",
        "project": project.to_dict(),
    }
    files: dict[str, bytes] = {}
    for a in project.assets.values():
        files[a.archive_path] = a.data
    for name, data in project.sources.items():
        files[f"sources/{name}"] = data
    return manifest, files


def write_archive(path: Path, manifest: dict[str, Any], files: dict[str, bytes],
                  keep_backup: bool = True) -> None:
    """Atomically write the package: temp file -> verify -> replace (+ .bak)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
            for name, data in files.items():
                z.writestr(name, data)
        with zipfile.ZipFile(tmp) as z:  # verify before replacing the good copy
            if z.testzip() is not None:
                raise ProjectFormatError("Written archive failed verification")
        with open(tmp, "rb+") as fh:  # flush to disk before swapping in the new file
            os.fsync(fh.fileno())
        if keep_backup and path.exists():
            shutil.copy2(path, backup_path(path))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def backup_path(path: Path) -> Path:
    return Path(str(path) + ".bak")


def save_project(project: BookProject, path: Path, keep_backup: bool = True) -> None:
    manifest, files = snapshot_for_save(project)
    write_archive(Path(path), manifest, files, keep_backup)


def load_project(path: Path, backup_dir: Path | None = None) -> BookProject:
    """Open a project. Raises ProjectFormatError for corrupt/unsafe packages."""
    path = Path(path)
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ProjectFormatError(f"Cannot open project: {e}") from e
    with z:
        infos = z.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ProjectFormatError("Archive contains too many entries")
        total = 0
        for info in infos:
            if not _safe_member(info.filename.rstrip("/")):
                raise ProjectFormatError(f"Unsafe path in archive: {info.filename!r}")
            if info.file_size > MAX_MEMBER_SIZE:
                raise ProjectFormatError(f"Archive entry too large: {info.filename}")
            total += info.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED:
            raise ProjectFormatError("Archive is unreasonably large")
        try:
            manifest = json.loads(z.read(MANIFEST).decode("utf-8"))
        except (KeyError, ValueError, zipfile.BadZipFile) as e:
            raise ProjectFormatError(f"Missing or invalid manifest: {e}") from e
        if manifest.get("format") != FORMAT_NAME or "project" not in manifest:
            raise ProjectFormatError("Not a BookForge project file")
        data = manifest["project"]
        data.setdefault("schema_version", manifest.get("schema_version", 0))
        if needs_migration(data):
            # Backup copy before touching an older project.
            try:
                shutil.copy2(path, str(path) + f".v{data['schema_version']}.bak")
            except OSError:
                pass
            try:
                data = migrate(data)
            except MigrationError as e:
                raise ProjectFormatError(str(e)) from e
        elif int(data["schema_version"]) > SCHEMA_VERSION:
            raise ProjectFormatError(
                f"Project schema {data['schema_version']} is newer than supported ({SCHEMA_VERSION})")
        try:
            project = BookProject.from_dict(data)
        except (TypeError, KeyError, ValueError) as e:
            raise ProjectFormatError(f"Project data is malformed: {e}") from e
        names = set(z.namelist())
        for asset in project.assets.values():
            if asset.archive_path in names:
                asset.data = z.read(asset.archive_path)
            # Missing assets keep empty data; validation reports them.
        for n in names:
            if n.startswith("sources/") and not n.endswith("/"):
                project.sources[n[len("sources/"):]] = z.read(n)
    return project


def recover_from_backup(path: Path) -> BookProject:
    """Load the `.bak` copy that save_project keeps next to the project."""
    bak = backup_path(Path(path))
    if not bak.exists():
        raise ProjectFormatError("No backup copy exists for this project")
    return load_project(bak)


def relink_asset(project: BookProject, asset_id: str, file_path: Path) -> Asset:
    """Attach a replacement file to an asset whose binary is missing."""
    import hashlib
    import io

    from PIL import Image
    asset = project.assets[asset_id]
    data = Path(file_path).read_bytes()
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
        im.verify()
    asset.data, asset.width, asset.height = data, w, h
    asset.sha256 = hashlib.sha256(data).hexdigest()
    asset.source_path = str(file_path)
    return asset
