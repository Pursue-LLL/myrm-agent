"""Volume backup store: persistence, listing order, id safety and crash safety.

[INPUT]
app.services.memory.backup.volume_store::VolumeBackupStore/BackupNotFoundError

[OUTPUT]
Save/list/load/delete behavior, path-traversal rejection and partial-write cleanup tests.

[POS]
Pure filesystem tests against a temporary backup root; no memory stores are involved.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.memory.backup import volume_store
from app.services.memory.backup.snapshot import MemorySnapshot, SnapshotError
from app.services.memory.backup.volume_store import BackupNotFoundError, VolumeBackupStore


def _snapshot(*contents: str) -> MemorySnapshot:
    return MemorySnapshot(
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
        memories={"semantic": [{"content": content} for content in contents]},
    )


def test_save_then_load_returns_the_same_snapshot_with_accurate_metadata(tmp_path: Path) -> None:
    store = VolumeBackupStore(tmp_path)
    snapshot = _snapshot("alpha", "beta")

    metadata = store.save(snapshot, "before the upgrade")

    assert metadata.memory_count == 2
    assert metadata.collections == ["semantic"]
    assert metadata.description == "before the upgrade"
    assert metadata.size_bytes == (tmp_path / metadata.backup_id / "snapshot.json.gz").stat().st_size
    assert store.load(metadata.backup_id) == snapshot
    assert store.list_backups() == [metadata]


def test_list_returns_newest_first_and_an_empty_list_for_a_missing_root(tmp_path: Path) -> None:
    assert VolumeBackupStore(tmp_path / "does-not-exist").list_backups() == []

    store = VolumeBackupStore(tmp_path)
    first = store.save(_snapshot("one"))
    second = store.save(_snapshot("two"))

    assert [backup.backup_id for backup in store.list_backups()] == [second.backup_id, first.backup_id]


def test_delete_removes_only_the_requested_backup(tmp_path: Path) -> None:
    store = VolumeBackupStore(tmp_path)
    kept = store.save(_snapshot("kept"))
    removed = store.save(_snapshot("removed"))

    assert store.delete(removed.backup_id) is True
    assert store.delete(removed.backup_id) is False
    assert [backup.backup_id for backup in store.list_backups()] == [kept.backup_id]


@pytest.mark.parametrize("backup_id", ["..", ".", "../outside", "/etc", "memory_x", "sandbox_20260101_000000_abcdef12", ""])
def test_ids_outside_the_generated_format_never_reach_the_filesystem(tmp_path: Path, backup_id: str) -> None:
    root = tmp_path / "backups"
    store = VolumeBackupStore(root)
    store.save(_snapshot("kept"))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "metadata.json").write_text("{}", encoding="utf-8")

    assert store.delete(backup_id) is False
    with pytest.raises(BackupNotFoundError):
        store.load(backup_id)

    assert (outside / "metadata.json").exists()
    assert len(store.list_backups()) == 1


def test_load_of_a_corrupt_snapshot_raises_a_snapshot_error(tmp_path: Path) -> None:
    store = VolumeBackupStore(tmp_path)
    metadata = store.save(_snapshot("alpha"))
    (tmp_path / metadata.backup_id / "snapshot.json.gz").write_bytes(b"damaged")

    with pytest.raises(SnapshotError, match="corrupt"):
        store.load(metadata.backup_id)


def test_list_skips_unreadable_and_foreign_directories_but_reports_the_unreadable_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = VolumeBackupStore(tmp_path)
    good = store.save(_snapshot("good"))
    broken = store.save(_snapshot("broken"))
    (tmp_path / broken.backup_id / "metadata.json").write_text("{not json", encoding="utf-8")
    # Pre-snapshot-format directories and unrelated folders are not backups of this store.
    legacy = tmp_path / "sandbox_20260101_000000_abcdef12"
    legacy.mkdir()
    (legacy / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes").mkdir()

    with caplog.at_level(logging.WARNING, logger=volume_store.logger.name):
        backups = store.list_backups()

    assert [backup.backup_id for backup in backups] == [good.backup_id]
    assert broken.backup_id in caplog.text


def test_a_failed_save_leaves_no_partial_backup_behind(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "backups"
    store = VolumeBackupStore(root)
    original_write = volume_store._write_atomically

    def fail_on_metadata(path: Path, data: bytes) -> None:
        if path.name == "metadata.json":
            raise OSError("disk full")
        original_write(path, data)

    monkeypatch.setattr(volume_store, "_write_atomically", fail_on_metadata)

    with pytest.raises(OSError, match="disk full"):
        store.save(_snapshot("alpha"))

    assert list(root.iterdir()) == []
