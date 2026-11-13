"""create_backup is serialized per process: callers on different threads never interleave a snapshot."""

from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from myrm_agent_harness.infra import sqlite_backup
from myrm_agent_harness.infra.sqlite_backup import BackupRecord, SQLiteBackupManager

_CALLERS = 6


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, data TEXT)")
    conn.executemany("INSERT INTO items (data) VALUES (?)", [(f"row-{i}",) for i in range(50)])
    conn.commit()
    conn.close()


def _backup_from_many_threads(manager: SQLiteBackupManager) -> list[BackupRecord]:
    with ThreadPoolExecutor(max_workers=_CALLERS) as pool:
        return list(pool.map(lambda _: manager.create_backup(), range(_CALLERS)))


def test_only_one_backup_copies_at_a_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "app.db"
    _create_db(db)
    manager = SQLiteBackupManager(db, tmp_path / "backups")

    real_copy = sqlite_backup.hot_copy_database
    guard = threading.Lock()
    active = 0
    peak = 0

    def observed_copy(src: str | Path, dst: str | Path) -> None:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        try:
            time.sleep(0.03)  # long enough for every other caller to reach the copy if nothing held them back
            real_copy(src, dst)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(sqlite_backup, "hot_copy_database", observed_copy)

    records = _backup_from_many_threads(manager)

    assert len({record.backup_id for record in records}) == _CALLERS
    assert peak == 1


def test_concurrent_backups_leave_a_consistent_manifest(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _create_db(db)
    manager = SQLiteBackupManager(db, tmp_path / "backups", retention=3)

    _backup_from_many_threads(manager)

    snapshots = tmp_path / "backups" / "snapshots"
    listed = {record.file_name for record in manager.list_backups()}
    on_disk = {path.name for path in snapshots.glob("backup-*.sqlite")}
    assert len(listed) == 3
    assert listed == on_disk
    assert not list(snapshots.glob(".tmp-*"))
