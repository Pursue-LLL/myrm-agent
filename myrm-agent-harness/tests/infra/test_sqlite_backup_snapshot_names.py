"""A backup never takes the name of a published snapshot, however close in time two backups start.

Snapshot ids are millisecond timestamps, and a backup of a small database finishes in about a millisecond. A clock
whose readings all fall in one millisecond stands in for the fast machine on which consecutive backups start together.
"""

from __future__ import annotations

import itertools
import sqlite3
import time
from pathlib import Path

import pytest

from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

_BACKUPS = 6
# Strictly increasing readings keep the recorded creation times ordered; 1 µs apart they stay inside the millisecond
# for far more reads than a handful of backups make.
_TICK_SECONDS = 1e-6


def _create_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, data TEXT)")
    conn.executemany("INSERT INTO items (data) VALUES (?)", [(f"row-{i}",) for i in range(20)])
    conn.commit()
    conn.close()


@pytest.fixture
def one_millisecond(monkeypatch: pytest.MonkeyPatch) -> int:
    """Make every clock reading of the test fall in one millisecond; return that millisecond."""
    millisecond = int(time.time() * 1000)
    start = (millisecond + 0.1) / 1000
    ticks = itertools.count()
    monkeypatch.setattr(time, "time", lambda: start + next(ticks) * _TICK_SECONDS)
    return millisecond


@pytest.mark.usefixtures("one_millisecond")
@pytest.mark.parametrize("retention", [1, 3])
def test_backups_started_in_one_millisecond_keep_the_manifest_and_the_disk_in_step(
    tmp_path: Path, retention: int
) -> None:
    db = tmp_path / "app.db"
    _create_db(db)
    manager = SQLiteBackupManager(db, tmp_path / "backups", retention=retention)
    snapshots = tmp_path / "backups" / "snapshots"

    for published in range(1, _BACKUPS + 1):
        manager.create_backup()

        listed = {record.file_name for record in manager.list_backups()}
        on_disk = {path.name for path in snapshots.glob("backup-*.sqlite")}
        assert len(listed) == min(published, retention)
        assert listed == on_disk


def test_a_backup_leaves_a_published_snapshot_untouched(tmp_path: Path, one_millisecond: int) -> None:
    db = tmp_path / "app.db"
    _create_db(db)
    snapshots = tmp_path / "backups" / "snapshots"
    snapshots.mkdir(parents=True)
    taken = snapshots / f"backup-{one_millisecond}.sqlite"
    taken.write_bytes(b"an earlier snapshot")

    record = SQLiteBackupManager(db, tmp_path / "backups").create_backup()

    assert record.file_name != taken.name
    assert taken.read_bytes() == b"an earlier snapshot"
    assert (snapshots / record.file_name).is_file()
