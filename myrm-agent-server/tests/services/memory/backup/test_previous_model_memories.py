"""Backups while an embedding switch has left memories under a previous model.

[INPUT]
app.services.memory.backup.snapshot::capture_snapshot/PreviousModelMemoriesError
app.services.memory.backup.service::MemoryBackupService
app.services.memory.backup.volume_store::VolumeBackupStore

[OUTPUT]
What capture and the local backup service do while such memories exist, and once they are migrated.

[POS]
Real MemoryManager on real embedded Qdrant + SQLite (only embeddings are offline). A snapshot holds what the current
model sees, so while memories sit under a previous model it would silently omit them: capture refuses instead, except
for the safety copy of a replacing restore, which leaves those memories in place.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory._manager.reindex import OrphanCollectionInfo
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores

from app.services.memory.backup.service import PRE_RESTORE_DESCRIPTION, MemoryBackupService
from app.services.memory.backup.snapshot import PreviousModelMemoriesError, SnapshotError, capture_snapshot
from app.services.memory.backup.volume_store import VolumeBackupStore
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

LEFT_BEHIND = 3


async def _write_under_a_previous_model(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave memories behind in the way an embedding switch does: written under one model, read under another."""
    async with offline_memory_manager(base, monkeypatch, embedding_model="previous/model") as previous:
        for index in range(LEFT_BEHIND):
            await previous.add_knowledge(f"Written before the switch, number {index}.")
    await clear_embedded_stores()


async def test_capture_refuses_while_a_previous_model_holds_memories(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await _write_under_a_previous_model(tmp_path / "memory", monkeypatch)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await manager.add_knowledge("Written under the current model.")

        with pytest.raises(PreviousModelMemoriesError, match=rf"\({LEFT_BEHIND}\)"):
            await capture_snapshot(manager)


async def test_capture_can_leave_previous_model_memories_out_on_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    await _write_under_a_previous_model(tmp_path / "memory", monkeypatch)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await manager.add_knowledge("Written under the current model.")

        snapshot = await capture_snapshot(manager, allow_previous_models=True)

    assert snapshot.memory_count == 1


async def test_capture_succeeds_once_the_previous_model_memories_are_migrated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _write_under_a_previous_model(tmp_path / "memory", monkeypatch)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        migration = await manager.reindex_from_orphans()
        assert (migration.migrated, migration.failed) == (LEFT_BEHIND, 0)

        snapshot = await capture_snapshot(manager)

    assert snapshot.memory_count == LEFT_BEHIND


async def test_capture_is_unaffected_when_no_embedding_model_was_ever_switched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await manager.add_knowledge("Written under the only model there has been.")

        snapshot = await capture_snapshot(manager)

    assert snapshot.memory_count == 1


async def test_capture_ignores_previous_model_memories_of_types_no_snapshot_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verbatim conversations are not part of a backup, so they cannot make one incomplete."""

    async def only_conversations() -> list[OrphanCollectionInfo]:
        return [OrphanCollectionInfo(collection_name="old_conversation", memory_type="conversation", document_count=4)]

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        monkeypatch.setattr(manager, "detect_orphan_collections", only_conversations)

        snapshot = await capture_snapshot(manager)

    assert snapshot.memory_count == 0


async def test_capture_refuses_when_it_cannot_tell_whether_memories_are_left_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unreachable() -> list[OrphanCollectionInfo]:
        raise RuntimeError("vector store at 10.0.0.7 is unreachable")

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        monkeypatch.setattr(manager, "detect_orphan_collections", unreachable)

        with pytest.raises(SnapshotError) as refused:
            await capture_snapshot(manager)

    assert not isinstance(refused.value, PreviousModelMemoriesError)
    assert "10.0.0.7" not in str(refused.value)


async def test_local_backup_is_refused_and_nothing_is_saved_while_a_previous_model_holds_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    await _write_under_a_previous_model(tmp_path / "memory", monkeypatch)

    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        with pytest.raises(PreviousModelMemoriesError):
            await MemoryBackupService(manager, store).create("manual")

    assert store.list_backups() == []


async def test_overwrite_restore_still_works_and_leaves_previous_model_memories_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "source", monkeypatch) as source:
        await source.add_knowledge("Kept in the backup.")
        backup = await MemoryBackupService(source, store).create("complete")
    await clear_embedded_stores()
    await _write_under_a_previous_model(tmp_path / "target", monkeypatch)

    async with offline_memory_manager(tmp_path / "target", monkeypatch) as target:
        restored = await MemoryBackupService(target, store).restore(backup.backup_id, overwrite=True)

        assert restored == 1
        assert (await target.estimate_reindex()).total_memories == LEFT_BEHIND
    safety_copies = [b for b in store.list_backups() if b.description == PRE_RESTORE_DESCRIPTION]
    assert len(safety_copies) == 1
