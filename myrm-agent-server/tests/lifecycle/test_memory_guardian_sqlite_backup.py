"""Tests for the SQLite hot-backup step that closes a memory maintenance cycle."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

from app.lifecycle.memory_guardian_ops import run_sqlite_backup

_MANAGER_FACTORY = "app.database.operations.backup.get_sqlite_backup_manager"


def _file_backed_manager(tmp_path: Path) -> SQLiteBackupManager:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('v1')")
    conn.commit()
    conn.close()
    return SQLiteBackupManager(db_path=db_path, backup_dir=tmp_path / "sqlite_backups")


@pytest.mark.asyncio
async def test_writes_a_verified_snapshot_of_the_live_database(tmp_path: Path) -> None:
    manager = _file_backed_manager(tmp_path)

    with patch(_MANAGER_FACTORY, return_value=manager):
        await run_sqlite_backup()

    [record] = manager.list_backups()
    assert record.quick_check == "ok"
    assert (tmp_path / "sqlite_backups" / "snapshots" / record.file_name).exists()


@pytest.mark.asyncio
async def test_skips_quietly_when_the_database_is_not_file_backed() -> None:
    with patch(_MANAGER_FACTORY, return_value=None):
        await run_sqlite_backup()


@pytest.mark.asyncio
async def test_copies_pages_off_the_event_loop() -> None:
    copy_threads: list[int] = []

    def create_backup() -> SimpleNamespace:
        copy_threads.append(threading.get_ident())
        return SimpleNamespace(file_name="snapshot.db", size_bytes=2048)

    with patch(_MANAGER_FACTORY, return_value=SimpleNamespace(create_backup=create_backup)):
        await run_sqlite_backup()

    assert copy_threads
    assert copy_threads[0] != threading.get_ident()


@pytest.mark.asyncio
async def test_a_failing_backup_is_logged_and_never_fails_the_cycle(caplog: pytest.LogCaptureFixture) -> None:
    manager = SimpleNamespace(create_backup=MagicMock(side_effect=OSError("disk full")))

    with patch(_MANAGER_FACTORY, return_value=manager), caplog.at_level(logging.WARNING):
        await run_sqlite_backup()

    assert "disk full" in caplog.text
