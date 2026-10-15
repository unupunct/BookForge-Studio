"""Schema migrations for saved projects.

Each migration upgrades the project dict from version N to N+1. The framework
is exercised by tests with synthetic migrations; production migrations are
registered in MIGRATIONS as the schema evolves.
"""
from __future__ import annotations

from typing import Any, Callable

from ..domain.book import SCHEMA_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]

# from_version -> function producing from_version + 1
MIGRATIONS: dict[int, Migration] = {}


class MigrationError(Exception):
    pass


def needs_migration(data: dict[str, Any], target: int = SCHEMA_VERSION) -> bool:
    return int(data.get("schema_version", 0)) < target


def migrate(data: dict[str, Any], target: int = SCHEMA_VERSION,
            migrations: dict[int, Migration] | None = None) -> dict[str, Any]:
    migrations = MIGRATIONS if migrations is None else migrations
    version = int(data.get("schema_version", 0))
    if version > target:
        raise MigrationError(
            f"Project schema {version} is newer than this application supports ({target}).")
    while version < target:
        fn = migrations.get(version)
        if fn is None:
            raise MigrationError(f"No migration available from schema {version} to {version + 1}.")
        data = fn(data)
        version += 1
        data["schema_version"] = version
    return data
