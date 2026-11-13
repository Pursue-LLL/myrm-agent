"""Tests for the pre-migration safety snapshot in init_database().

The snapshot (get_sqlite_backup_manager() → create_backup()) is taken before run_migrations() only while a
migration is pending, and off the event loop: a start with nothing to migrate must not copy the whole database.
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


@contextmanager
def _patched_init_database(
    manager: MagicMock | None,
    *,
    pending: bool,
    run_migrations: AsyncMock,
) -> Iterator[None]:
    """Swap everything init_database() touches for fakes; the schema gate runs against a MagicMock engine."""
    fake_engine = MagicMock()
    fake_conn = AsyncMock()
    fake_engine.begin.return_value.__aenter__ = AsyncMock(return_value=fake_conn)
    fake_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.database.connection.get_database_engine", return_value=fake_engine),
        patch("app.database.migrations.run_migrations", run_migrations),
        patch("app.database.migrations.create_indexes", new_callable=AsyncMock),
        patch("app.database.migrations.has_pending_migrations", new_callable=AsyncMock, return_value=pending),
        patch("app.database.operations.backup.get_sqlite_backup_manager", return_value=manager),
    ):
        yield


@pytest.mark.asyncio
async def test_init_database_calls_backup_before_migrations():
    """With a migration pending, create_backup() must execute before run_migrations()."""
    call_order: list[str] = []

    mock_manager = MagicMock(spec=SQLiteBackupManager)
    mock_manager.create_backup.side_effect = lambda: call_order.append("backup") or MagicMock()

    async def fake_run_migrations(engine: object) -> None:
        call_order.append("migrations")

    with _patched_init_database(mock_manager, pending=True, run_migrations=AsyncMock(side_effect=fake_run_migrations)):
        from app.database.connection import init_database

        await init_database()

    assert call_order == ["backup", "migrations"]


@pytest.mark.asyncio
async def test_init_database_takes_no_snapshot_when_nothing_is_pending():
    """A start with every migration recorded must not copy the database, yet still runs the (no-op) migration pass."""
    mock_manager = MagicMock(spec=SQLiteBackupManager)
    mock_run_migrations = AsyncMock()

    with _patched_init_database(mock_manager, pending=False, run_migrations=mock_run_migrations):
        from app.database.connection import init_database

        await init_database()

    mock_manager.create_backup.assert_not_called()
    mock_run_migrations.assert_awaited_once()


@pytest.mark.asyncio
async def test_init_database_copies_the_database_off_the_event_loop():
    """The snapshot of a grown database takes seconds; it must not hold the loop that other startup work shares."""
    loop_thread = threading.get_ident()
    backup_threads: list[int] = []

    mock_manager = MagicMock(spec=SQLiteBackupManager)
    mock_manager.create_backup.side_effect = lambda: backup_threads.append(threading.get_ident()) or MagicMock()

    with _patched_init_database(mock_manager, pending=True, run_migrations=AsyncMock()):
        from app.database.connection import init_database

        await init_database()

    assert len(backup_threads) == 1
    assert backup_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_init_database_aborts_when_backup_fails_with_manager():
    """If create_backup() raises when manager exists, init_database() must abort (fail-closed).

    Critically verifies that run_migrations is NEVER called when backup fails,
    preventing destructive DDL without a safety net.
    """
    mock_manager = MagicMock(spec=SQLiteBackupManager)
    mock_manager.create_backup.side_effect = OSError("disk full")
    mock_run_migrations = AsyncMock()

    with _patched_init_database(mock_manager, pending=True, run_migrations=mock_run_migrations):
        from app.database.connection import init_database

        with pytest.raises(OSError, match="disk full"):
            await init_database()

    mock_run_migrations.assert_not_called()


@pytest.mark.asyncio
async def test_init_database_skips_backup_when_manager_is_none():
    """If get_sqlite_backup_manager() returns None (in-memory), backup is skipped gracefully."""
    mock_run_migrations = AsyncMock()

    with _patched_init_database(None, pending=True, run_migrations=mock_run_migrations):
        from app.database.connection import init_database

        await init_database()

    mock_run_migrations.assert_awaited_once()


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
