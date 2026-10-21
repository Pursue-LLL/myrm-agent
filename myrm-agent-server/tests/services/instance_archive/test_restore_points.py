"""Restore points: consistent snapshots, verified staging, swap at the next boot."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from app.services.instance_archive import (
    ArchivePaths,
    OutcomeStatus,
    RestorePointError,
    create_pre_update_point,
    create_restore_point,
    delete_restore_point,
    list_restore_points,
    prepare_rollback,
    run_pending_promotion,
    stage_restore,
)
from app.services.instance_archive.restore_points import PRE_UPDATE_LABEL_PREFIX, parse_pre_update_label
from tests.services.instance_archive.conftest import create_instance_db


def _chats(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return sorted(row[0] for row in conn.execute("SELECT id FROM chats"))
    finally:
        conn.close()


def _state(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    conn = create_instance_db(state / "data.db")
    conn.execute("INSERT INTO chats VALUES ('before', 'x', NULL, NULL, 0)")
    conn.commit()
    conn.close()
    side = sqlite3.connect(state / "checkpoints.db")
    side.execute("CREATE TABLE cp (v TEXT)")
    side.execute("INSERT INTO cp VALUES ('before')")
    side.commit()
    side.close()
    return state


def _mutate(state: Path) -> None:
    conn = sqlite3.connect(state / "data.db")
    conn.execute("DELETE FROM chats")
    conn.execute("INSERT INTO chats VALUES ('after', 'y', NULL, NULL, 0)")
    conn.commit()
    conn.close()
    side = sqlite3.connect(state / "checkpoints.db")
    side.execute("UPDATE cp SET v = 'after'")
    side.commit()
    side.close()


def test_restore_swaps_both_databases_at_the_next_boot(tmp_path: Path, dead_requester: Callable[[Path], None]) -> None:
    state = _state(tmp_path)
    point = create_restore_point(state, "manual")
    assert point.files == ["data.db", "checkpoints.db"]
    _mutate(state)

    pending = stage_restore(state, point.snapshot_id, max_schema_version=10)
    assert _chats(state / "data.db") == ["after"]  # nothing is written into the live database
    assert {"data.db", "data.db-wal", "data.db-shm", "checkpoints.db"} <= set(pending.entries)

    dead_requester(state)
    outcome = run_pending_promotion(state, wait_seconds=0)

    assert outcome is not None
    assert outcome.status is OutcomeStatus.RESTORED
    assert _chats(state / "data.db") == ["before"]
    side = sqlite3.connect(state / "checkpoints.db")
    assert side.execute("SELECT v FROM cp").fetchone() == ("before",)
    side.close()
    assert list_restore_points(state)  # the point itself is kept for reuse

    assert prepare_rollback(state) is not None
    dead_requester(state)
    run_pending_promotion(state, wait_seconds=0)
    assert _chats(state / "data.db") == ["after"]


def test_restore_rejects_a_snapshot_written_by_a_newer_schema(tmp_path: Path) -> None:
    state = _state(tmp_path)
    point = create_restore_point(state, "manual")

    with pytest.raises(RestorePointError) as rejected:
        stage_restore(state, point.snapshot_id, max_schema_version=2)

    assert rejected.value.code == "newer_schema"
    assert not ArchivePaths(state).pending.exists()
    assert not any(ArchivePaths(state).staging.glob("restore-*"))


def test_restore_rejects_a_tampered_snapshot(tmp_path: Path) -> None:
    state = _state(tmp_path)
    point = create_restore_point(state, "manual")
    with (state / "snapshots" / point.snapshot_id / "data.db").open("r+b") as handle:
        handle.seek(4096)
        handle.write(b"tampered")

    with pytest.raises(RestorePointError) as rejected:
        stage_restore(state, point.snapshot_id, max_schema_version=10)

    assert rejected.value.code == "restore_point_corrupt"


def test_unknown_or_traversing_ids_are_rejected(tmp_path: Path) -> None:
    state = _state(tmp_path)
    for bad in ("snap_missing", "../state", ".."):
        with pytest.raises(RestorePointError):
            stage_restore(state, bad, max_schema_version=10)
    for traversing in ("../state", "..", "a/b"):
        with pytest.raises(RestorePointError):
            delete_restore_point(state, traversing)
    assert delete_restore_point(state, "snap_missing") is False
    assert (state / "data.db").exists()


def test_second_restore_cannot_be_queued_while_one_is_pending(tmp_path: Path) -> None:
    state = _state(tmp_path)
    point = create_restore_point(state, "manual")
    stage_restore(state, point.snapshot_id, max_schema_version=10)

    with pytest.raises(RestorePointError) as rejected:
        stage_restore(state, point.snapshot_id, max_schema_version=10)

    assert rejected.value.code == "operation_pending"


def test_pre_update_retention_keeps_manual_points(tmp_path: Path) -> None:
    state = _state(tmp_path)
    manual = create_restore_point(state, "my own point")
    for index in range(4):
        create_pre_update_point(state, from_version=f"1.{index}", to_version=f"1.{index + 1}", keep_latest=2)

    labels = [p.label for p in list_restore_points(state)]
    assert sum(label.startswith(PRE_UPDATE_LABEL_PREFIX) for label in labels) == 2
    assert manual.snapshot_id in {p.snapshot_id for p in list_restore_points(state)}
    newest = list_restore_points(state)[0]
    assert (newest.from_version, newest.to_version) == ("1.3", "1.4")


def test_points_listing_extra_files_in_a_sidecar_stay_restorable(tmp_path: Path) -> None:
    state = _state(tmp_path)
    sidecar = state / "snapshots" / "snap_sidecar"
    sidecar.mkdir(parents=True)
    (sidecar / "data.db").write_bytes((state / "data.db").read_bytes())
    (sidecar / "checkpoints.db").write_bytes((state / "checkpoints.db").read_bytes())
    (sidecar / "meta.json").write_text(
        json.dumps({"snapshot_id": "snap_sidecar", "label": "pre-update:1.0->1.1", "size_bytes": 1, "created_at": "2026-01-01"})
    )
    (sidecar / "extra_files.json").write_text(json.dumps({"files": ["checkpoints.db"]}))

    [point] = list_restore_points(state)

    assert point.files == ["data.db", "checkpoints.db"]
    assert stage_restore(state, "snap_sidecar", max_schema_version=10).entries


def test_parse_pre_update_label() -> None:
    assert parse_pre_update_label("pre-update:1.0->1.1") == ("1.0", "1.1")
    assert parse_pre_update_label("pre-update:1.0->") == (None, None)
    assert parse_pre_update_label("manual") == (None, None)
