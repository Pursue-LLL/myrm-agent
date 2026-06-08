"""Tests for app.database.backup — SQLite backup manager factory."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


def test_factory_returns_manager_for_valid_db(tmp_path: Path) -> None:
    """get_sqlite_backup_manager() returns a configured manager when DB exists."""
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.commit()
    conn.close()

    with patch("app.database.backup.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.database.backup import get_sqlite_backup_manager

        mgr = get_sqlite_backup_manager()

    assert mgr is not None
    assert isinstance(mgr, SQLiteBackupManager)


def test_factory_returns_none_for_memory_db() -> None:
    """get_sqlite_backup_manager() returns None for :memory: databases."""
    with patch("app.database.backup.settings") as mock_settings:
        mock_settings.database.sqlite_path = ":memory:"
        from app.database.backup import get_sqlite_backup_manager

        mgr = get_sqlite_backup_manager()

    assert mgr is None


def test_factory_returns_none_for_nonexistent_db(tmp_path: Path) -> None:
    """get_sqlite_backup_manager() returns None when the DB file doesn't exist."""
    db = tmp_path / "nonexistent.db"

    with patch("app.database.backup.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.database.backup import get_sqlite_backup_manager

        mgr = get_sqlite_backup_manager()

    assert mgr is None


def test_factory_backup_dir_convention(tmp_path: Path) -> None:
    """The factory must place backups under <db_parent>/sqlite_backups/."""
    db = tmp_path / "data" / "app.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.commit()
    conn.close()

    with patch("app.database.backup.settings") as mock_settings:
        mock_settings.database.sqlite_path = str(db)
        from app.database.backup import get_sqlite_backup_manager

        mgr = get_sqlite_backup_manager()

    assert mgr is not None
    record = mgr.create_backup()
    assert record.quick_check == "ok"
    expected_backup_dir = db.parent / "sqlite_backups" / "snapshots"
    assert expected_backup_dir.exists()
