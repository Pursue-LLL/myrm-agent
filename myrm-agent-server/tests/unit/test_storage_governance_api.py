"""Tests for System Storage Governance API handler functions."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.api.system.router import (
    create_state_snapshot,
    delete_state_snapshot,
    execute_storage_compaction,
    get_storage_governance_report,
    restore_state_snapshot,
)
from app.api.system.schemas import CreateSnapshotRequest, StorageCompactionRequest


def _create_database(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INT);")
    conn.execute("INSERT INTO t VALUES (1);")
    conn.commit()
    conn.close()


@pytest.fixture
def state_dir(tmp_path: Path) -> Iterator[Path]:
    """A state directory holding the state database and the checkpoint database, wired in as the server's settings."""
    _create_database(tmp_path / "data.db")
    _create_database(tmp_path / "checkpoints.db")
    mock_settings = MagicMock()
    mock_settings.database.state_dir = str(tmp_path)
    mock_settings.database.sqlite_db_path = str(tmp_path / "checkpoints.db")
    mock_disk = MagicMock(total=100_000_000_000, free=80_000_000_000, used=20_000_000_000)
    with (
        patch("app.api.system.router.get_settings", return_value=mock_settings),
        patch("shutil.disk_usage", return_value=mock_disk),
    ):
        yield tmp_path


def test_governance_report_attributes_the_checkpoint_database(state_dir: Path) -> None:
    report = get_storage_governance_report()

    assert report.total_storage_bytes > 0
    assert len(report.categories) == 7
    checkpoints = next(c for c in report.categories if c.category == "checkpoints")
    assert checkpoints.bytes == (state_dir / "checkpoints.db").stat().st_size > 0
    assert isinstance(report.is_growth_healthy, bool)


def test_compaction_reports_the_state_database_it_compacted(state_dir: Path) -> None:
    comp_res = execute_storage_compaction(StorageCompactionRequest(incremental_pages=100))

    assert comp_res.success is True
    assert comp_res.wal_truncated is True
    assert comp_res.initial_bytes == (state_dir / "data.db").stat().st_size


def test_state_snapshot_handlers_round_trip(state_dir: Path) -> None:
    snap_res = create_state_snapshot(CreateSnapshotRequest(label="test_handler_snapshot"))
    assert snap_res.success is True
    assert snap_res.snapshot is not None
    snap_id = snap_res.snapshot.snapshot_id

    restore_res = restore_state_snapshot(snap_id)
    assert restore_res.success is True

    del_res = delete_state_snapshot(snap_id)
    assert del_res.success is True
