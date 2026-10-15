"""Locations of per-user data (settings, user templates, recovery files)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def user_data_dir() -> Path:
    override = os.environ.get("BOOKFORGE_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "BookForgeStudio"
    else:
        base = Path.home() / ".local" / "share" / "BookForgeStudio"
    base.mkdir(parents=True, exist_ok=True)
    return base


def user_templates_dir() -> Path:
    p = user_data_dir() / "templates"
    p.mkdir(parents=True, exist_ok=True)
    return p


def recovery_dir() -> Path:
    p = user_data_dir() / "recovery"
    p.mkdir(parents=True, exist_ok=True)
    return p


def builtin_templates_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "app" / "templates"
    return Path(__file__).resolve().parents[1] / "templates"
