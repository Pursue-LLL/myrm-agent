"""Tests for System Storage Governance API handler functions."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api.system.router import (
    create_state_snapshot,
    delete_state_snapshot,
    get_storage_governance_report,
    restore_state_snapshot,
)
from app.api.system.schemas import CreateSnapshotRequest, StorageGovernanceReportResponse
from app.config.settings import DatabaseSettings


def _create_database(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE t (x INT);")
    conn.execute("INSERT INTO t VALUES (1);")
    conn.commit()
    conn.close()


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


@pytest.fixture
def state_dir(tmp_path: Path) -> Iterator[Path]:
    """A state directory holding the databases, wired in as the server's settings with memory kept on another volume."""
    _create_database(tmp_path / "data.db")
    _create_database(tmp_path / "checkpoints.db")
    database = DatabaseSettings.model_construct(
        state_dir=str(tmp_path),
        sqlite_path=str(tmp_path / "data.db"),
        sqlite_db_path=str(tmp_path / "checkpoints.db"),
        qdrant_path=str(tmp_path / "qdrant"),
        harness_dir=str(tmp_path / "harness"),
        event_log_dir=str(tmp_path / "event_logs"),
        memory_base_path=str(tmp_path.parent / f"{tmp_path.name}_memory"),
    )
    mock_disk = MagicMock(total=100_000_000_000, free=80_000_000_000, used=20_000_000_000)
    with (
        patch("app.api.system.router.get_settings", return_value=SimpleNamespace(database=database)),
        patch("shutil.disk_usage", return_value=mock_disk),
    ):
        yield tmp_path


def _bytes_by_category(report: StorageGovernanceReportResponse) -> dict[str, int]:
    return {c.category: c.bytes for c in report.categories}


def test_governance_report_attributes_the_checkpoint_database(state_dir: Path) -> None:
    report = get_storage_governance_report()

    assert report.total_storage_bytes > 0
    assert _bytes_by_category(report)["checkpoints"] == (state_dir / "checkpoints.db").stat().st_size > 0


def test_governance_report_covers_backups_relocated_memory_and_everything_else(state_dir: Path) -> None:
    _write(state_dir / "sqlite_backups" / "snapshots" / "backup.sqlite", 4000)
    _write(state_dir.parent / f"{state_dir.name}_memory" / "m.md", 600)
    _write(state_dir / "wiki" / "page.md", 90)

    report = get_storage_governance_report()

    by_category = _bytes_by_category(report)
    assert by_category["sqlite_backups"] == 4000
    assert by_category["memory_archive"] == 600
    assert by_category["other"] == 90
    assert [c.category for c in report.categories] == [
        "sqlite_database",
        "checkpoints",
        "workspaces",
        "vector_store",
        "memory_archive",
        "event_logs",
        "sqlite_backups",
        "snapshots",
        "other",
    ]
    assert report.total_storage_bytes == sum(by_category.values())


def test_a_created_snapshot_is_attributed_to_the_snapshots_category(state_dir: Path) -> None:
    assert _bytes_by_category(get_storage_governance_report())["snapshots"] == 0

    assert create_state_snapshot(CreateSnapshotRequest(label="ledger")).success is True

    assert _bytes_by_category(get_storage_governance_report())["snapshots"] > 0


def test_state_snapshot_handlers_round_trip(state_dir: Path) -> None:
    snap_res = create_state_snapshot(CreateSnapshotRequest(label="test_handler_snapshot"))
    assert snap_res.success is True
    assert snap_res.snapshot is not None
    snap_id = snap_res.snapshot.snapshot_id

    restore_res = restore_state_snapshot(snap_id)
    assert restore_res.success is True

    del_res = delete_state_snapshot(snap_id)
    assert del_res.success is True
