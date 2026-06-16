import importlib
import re
from importlib.resources import files as resource_files
from pathlib import Path
from typing import Any

from clickhouse_connect.driver import Client

from src.db.clickhouse import get_client

MIGRATIONS_TABLE = "schema_migrations"

_VERSION_RE = re.compile(r"^(\d{3})_.+\.py$")


def _ensure_migrations_table(client: Client) -> None:
    client.command(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} ("
        "    version UInt16,"
        "    name String,"
        "    applied_at DateTime DEFAULT now()"
        ") ENGINE = MergeTree "
        "ORDER BY version"
    )


def _get_applied_versions(client: Client) -> list[int]:
    rows = client.query(
        f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY version ASC"
    ).result_rows
    return [r[0] for r in rows]


def _discover_versions() -> dict[int, tuple[str, str]]:
    versions_dir = Path(__file__).parent / "versions"
    discovered: dict[int, tuple[str, str]] = {}
    for path in sorted(versions_dir.glob("*.py")):
        match = _VERSION_RE.match(path.name)
        if not match:
            continue
        version = int(match.group(1))
        module_name = path.stem
        short_name = path.name
        discovered[version] = (
            f"src.db.clickhouse.migrations.versions.{module_name}",
            short_name,
        )
    return discovered


def _load_version_module(version: int, module_path: str) -> Any:
    return importlib.import_module(module_path)


def _mark_applied(client: Client, version: int, name: str) -> None:
    client.command(
        f"INSERT INTO {MIGRATIONS_TABLE} (version, name) "
        f"VALUES ({version}, '{name}')"
    )


def _mark_removed(client: Client, version: int) -> None:
    client.command(
        f"ALTER TABLE {MIGRATIONS_TABLE} "
        f"DELETE WHERE version = {version}"
    )


def upgrade(client: Client | None = None) -> list[int]:
    c = client if client is not None else get_client()
    _ensure_migrations_table(c)
    applied = _get_applied_versions(c)
    all_versions = _discover_versions()

    applied_set = set(applied)
    new_versions: list[int] = []

    for version in sorted(all_versions):
        if version in applied_set:
            continue
        module_path, short_name = all_versions[version]
        mod = _load_version_module(version, module_path)
        if not hasattr(mod, "upgrade"):
            raise RuntimeError(
                f"Migration {version} ({module_path}) missing upgrade() function"
            )
        mod.upgrade(c)
        _mark_applied(c, version, short_name)
        new_versions.append(version)

    return new_versions


def downgrade(client: Client | None = None) -> int | None:
    c = client if client is not None else get_client()
    _ensure_migrations_table(c)
    applied = _get_applied_versions(c)
    if not applied:
        raise RuntimeError("No migrations have been applied.")
        return None

    latest_version = applied[-1]
    all_versions = _discover_versions()

    if latest_version not in all_versions:
        raise RuntimeError(
            f"Migration {latest_version} is applied but no version file found. "
        )

    module_path, _ = all_versions[latest_version]
    mod = _load_version_module(latest_version, module_path)

    if not hasattr(mod, "downgrade"):
        raise RuntimeError(
            f"Migration {latest_version} ({module_path}) has no downgrade() function."
        )

    mod.downgrade(c)
    _mark_removed(c, latest_version)
    return latest_version


def history(client: Client | None = None) -> list[dict[str, Any]]:
    c = client if client is not None else get_client()
    _ensure_migrations_table(c)
    rows = c.query(
        f"SELECT version, name, applied_at "
        f"FROM {MIGRATIONS_TABLE} "
        f"ORDER BY version ASC"
    ).result_rows
    return [
        {"version": r[0], "name": r[1], "applied_at": r[2]}
        for r in rows
    ]


def pending(client: Client | None = None) -> list[int]:
    c = client if client is not None else get_client()
    _ensure_migrations_table(c)
    applied = set(_get_applied_versions(c))
    all_versions = _discover_versions()
    return sorted(v for v in all_versions if v not in applied)


def check(client: Client | None = None) -> bool:
    return len(pending(client=client)) == 0
