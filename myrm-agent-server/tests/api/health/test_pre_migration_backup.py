"""Tests for pre-migration safety snapshot in init_database().

Verifies that get_sqlite_backup_manager() → create_backup() is called before
run_migrations() to protect multi-step DDL migrations from partial failure.
"""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


@pytest.mark.asyncio
async def test_init_database_calls_backup_before_migrations():
    """get_sqlite_backup_manager().create_backup() must execute before run_migrations()."""
    call_order: list[str] = []

    mock_manager = MagicMock(spec=SQLiteBackupManager)
    mock_manager.create_backup.side_effect = lambda: call_order.append("backup") or MagicMock()

    async def fake_run_migrations(engine: object) -> None:
        call_order.append("migrations")

    async def fake_create_indexes(engine: object) -> None:
        call_order.append("indexes")

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.backup.get_sqlite_backup_manager", return_value=mock_manager),
    ):
        from app.database.connection import init_database

        await init_database()

    assert "backup" in call_order, "create_backup was not called"
    assert "migrations" in call_order, "run_migrations was not called"
    backup_idx = call_order.index("backup")
    migrations_idx = call_order.index("migrations")
    assert backup_idx < migrations_idx, (
        f"backup must run before migrations, got order: {call_order}"
    )


@pytest.mark.asyncio
async def test_init_database_continues_when_backup_fails():
    """If get_sqlite_backup_manager() raises, init_database() must still proceed."""
    migrations_ran = False

    async def fake_run_migrations(engine: object) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    async def fake_create_indexes(engine: object) -> None:
        pass

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.backup.get_sqlite_backup_manager", side_effect=OSError("disk full")),
    ):
        from app.database.connection import init_database

        await init_database()

    assert migrations_ran, "run_migrations must execute even when backup fails"


@pytest.mark.asyncio
async def test_init_database_skips_backup_when_manager_is_none():
    """If get_sqlite_backup_manager() returns None (in-memory), backup is skipped gracefully."""
    migrations_ran = False

    async def fake_run_migrations(engine: object) -> None:
        nonlocal migrations_ran
        migrations_ran = True

    async def fake_create_indexes(engine: object) -> None:
        pass

    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", side_effect=fake_run_migrations),
        patch("app.database.migrations.create_indexes", side_effect=fake_create_indexes),
        patch("app.database.backup.get_sqlite_backup_manager", return_value=None),
    ):
        from app.database.connection import init_database

        await init_database()

    assert migrations_ran, "run_migrations must execute when backup manager is None"


# --- Integration tests: SQLiteBackupManager (real sqlite3) ---


def test_backup_manager_creates_verified_snapshot(tmp_path: Path):
    """SQLiteBackupManager.create_backup() produces a quick_check-verified snapshot."""
    db = tmp_path / "app.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('v1')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "sqlite_backups"
    manager = SQLiteBackupManager(db_path=db, backup_dir=backup_dir)
    record = manager.create_backup()

    assert record.quick_check == "ok"
    assert record.size_bytes > 0
    assert record.checksum_sha256

    snapshot = backup_dir / "snapshots" / record.file_name
    assert snapshot.exists()


def test_backup_then_restore_after_migration_failure(tmp_path: Path):
    """Simulates: backup -> destructive migration fails midway -> restore recovers data."""
    db = tmp_path / "migrate_fail.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cron_jobs (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO cron_jobs VALUES (1, 'daily_report')")
    conn.execute("INSERT INTO cron_jobs VALUES (2, 'weekly_sync')")
    conn.commit()
    conn.close()

    backup_dir = tmp_path / "sqlite_backups"
    manager = SQLiteBackupManager(db_path=db, backup_dir=backup_dir)
    manager.create_backup()

    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE cron_jobs_new AS SELECT id, name FROM cron_jobs")
    conn.execute("DROP TABLE cron_jobs")
    conn.close()

    result = manager.restore_latest()
    assert result.restored is True

    conn = sqlite3.connect(str(db))
    count = conn.execute("SELECT count(*) FROM cron_jobs").fetchone()[0]
    conn.close()
    assert count == 2


def test_backup_manager_on_nonexistent_db_creates_empty(tmp_path: Path):
    """SQLiteBackupManager.create_backup() on a missing file creates a new empty DB backup.

    sqlite3.connect() auto-creates the file, so it doesn't raise. The factory
    guards against this by returning None — tested in test_backup_factory.py.
    """
    missing = tmp_path / "nonexistent.db"
    backup_dir = tmp_path / "sqlite_backups"
    manager = SQLiteBackupManager(db_path=missing, backup_dir=backup_dir)

    record = manager.create_backup()
    assert record.quick_check == "ok"
    assert record.size_bytes > 0
