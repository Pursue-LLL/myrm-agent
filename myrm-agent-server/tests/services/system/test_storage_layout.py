"""The storage layout the server declares must match where the server really writes."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from myrm_agent_harness.observability.storage_governance import StorageCategory, StorageGovernanceInspector

from app.config.settings import DatabaseSettings
from app.database.operations.backup import backup_dir_for, get_sqlite_backup_manager
from app.services.system.storage_layout import build_storage_layout


def _settings(state_dir: Path, **relocated: str) -> DatabaseSettings:
    """Settings as `DatabaseSettings.resolve_paths` derives them, with chosen paths moved elsewhere."""
    paths = {
        "state_dir": str(state_dir),
        "sqlite_path": str(state_dir / "data.db"),
        "sqlite_db_path": str(state_dir / "checkpoints.db"),
        "qdrant_path": str(state_dir / "qdrant"),
        "harness_dir": str(state_dir / "harness"),
        "event_log_dir": str(state_dir / "event_logs"),
        "memory_base_path": str(state_dir / "memory"),
    }
    return DatabaseSettings.model_construct(**{**paths, **relocated})


def _create_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", ("x" * 2000,))
    conn.commit()
    conn.close()


def test_every_category_but_other_is_declared_from_the_settings(tmp_path: Path) -> None:
    layout = build_storage_layout(_settings(tmp_path))

    assert layout == {
        StorageCategory.SQLITE_DATABASE: (tmp_path / "data.db",),
        StorageCategory.CHECKPOINTS: (tmp_path / "checkpoints.db",),
        StorageCategory.WORKSPACES: (tmp_path / "harness",),
        StorageCategory.VECTOR_STORE: (tmp_path / "qdrant",),
        StorageCategory.MEMORY_ARCHIVE: (tmp_path / "memory",),
        StorageCategory.EVENT_LOGS: (tmp_path / "event_logs",),
        StorageCategory.SQLITE_BACKUPS: (tmp_path / "sqlite_backups",),
        StorageCategory.SNAPSHOTS: (tmp_path / "snapshots",),
    }
    assert set(layout) == set(StorageCategory) - {StorageCategory.OTHER}


def test_relocated_paths_are_declared_where_the_settings_put_them(tmp_path: Path) -> None:
    nas = tmp_path / "nas"

    layout = build_storage_layout(
        _settings(tmp_path / "state", memory_base_path=str(nas / "memory"), event_log_dir=str(nas / "logs"))
    )

    assert layout[StorageCategory.MEMORY_ARCHIVE] == (nas / "memory",)
    assert layout[StorageCategory.EVENT_LOGS] == (nas / "logs",)
    assert layout[StorageCategory.SQLITE_BACKUPS] == (tmp_path / "state" / "sqlite_backups",)


def test_the_backup_category_is_where_the_backup_manager_writes(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _create_database(state_dir / "data.db")
    settings = _settings(state_dir)

    with patch("app.database.operations.backup.settings", SimpleNamespace(database=settings)):
        manager = get_sqlite_backup_manager()
    assert manager is not None
    record = manager.create_backup()

    (backup_dir,) = build_storage_layout(settings)[StorageCategory.SQLITE_BACKUPS]
    assert backup_dir == backup_dir_for(state_dir / "data.db")
    assert (backup_dir / "snapshots" / record.file_name).is_file()

    report = StorageGovernanceInspector(state_dir, layout=build_storage_layout(settings)).inspect()
    backups = next(c for c in report.categories if c.category is StorageCategory.SQLITE_BACKUPS)
    assert backups.bytes >= (backup_dir / "snapshots" / record.file_name).stat().st_size > 0


def test_the_ledger_covers_the_state_directory_and_the_relocated_volume(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    nas = tmp_path / "nas"
    _create_database(state_dir / "data.db")
    _create_database(state_dir / "checkpoints.db")
    (state_dir / "harness" / "workspace").mkdir(parents=True)
    (state_dir / "harness" / "workspace" / "a.md").write_bytes(b"x" * 300)
    (state_dir / "skills" / "mine").mkdir(parents=True)
    (state_dir / "skills" / "mine" / "SKILL.md").write_bytes(b"x" * 70)
    (nas / "memory").mkdir(parents=True)
    (nas / "memory" / "m.md").write_bytes(b"x" * 50)
    settings = _settings(state_dir, memory_base_path=str(nas / "memory"))

    report = StorageGovernanceInspector(state_dir, layout=build_storage_layout(settings)).inspect()

    by_category = {c.category: c.bytes for c in report.categories}
    assert by_category[StorageCategory.MEMORY_ARCHIVE] == 50
    assert by_category[StorageCategory.WORKSPACES] == 300
    assert by_category[StorageCategory.OTHER] == 70
    on_disk = sum(f.stat().st_size for root in (state_dir, nas) for f in root.rglob("*") if f.is_file())
    assert report.total_storage_bytes == on_disk
