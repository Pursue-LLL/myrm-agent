"""Local backup service: create, merge restore and overwrite restore with its safety copy.

[INPUT]
app.services.memory.backup.service::MemoryBackupService
app.services.memory.backup.volume_store::VolumeBackupStore

[OUTPUT]
End-to-end service behavior on real memory stores and a real volume store.

[POS]
Proves the data-safety contract: a backup is complete or absent, a bad backup never costs the
user memories, and an overwrite restore always leaves a restorable copy of what it replaced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.services.memory.backup import service as service_module
from app.services.memory.backup.service import PRE_RESTORE_DESCRIPTION, MemoryBackupService
from app.services.memory.backup.snapshot import SnapshotError
from app.services.memory.backup.volume_store import BackupNotFoundError, VolumeBackupStore
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration


async def _knowledge(manager: MemoryManager) -> list[str]:
    return sorted(m.content for m in await manager.list_memories(MemoryType.SEMANTIC, limit=100))


async def test_create_then_overwrite_restore_brings_back_exactly_the_backed_up_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryBackupService(manager, store)
        await manager.add_knowledge("Kept in the backup.")
        await manager.add_rule("deploying", "run smoke tests first")
        backup = await service.create("nightly")
        await manager.add_knowledge("Added after the backup.")

        restored = await service.restore(backup.backup_id, overwrite=True)

        assert restored == 2
        assert await _knowledge(manager) == ["Kept in the backup."]
        assert await manager.count_memories(MemoryType.PROCEDURAL) == 1
    assert backup.description == "nightly"
    assert backup.memory_count == 2


async def test_overwrite_restore_first_saves_what_it_replaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryBackupService(manager, store)
        await manager.add_knowledge("Kept in the backup.")
        backup = await service.create()
        await manager.add_knowledge("Only in the live store.")

        await service.restore(backup.backup_id, overwrite=True)

    safety_copies = [b for b in store.list_backups() if b.description == PRE_RESTORE_DESCRIPTION]
    assert len(safety_copies) == 1
    safety = store.load(safety_copies[0].backup_id)
    assert sorted(entry["content"] for entry in safety.memories["semantic"]) == [
        "Kept in the backup.",
        "Only in the live store.",
    ]


async def test_merge_restore_keeps_live_memories_and_saves_no_safety_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryBackupService(manager, store)
        await manager.add_knowledge("Kept in the backup.")
        backup = await service.create()
        await manager.add_knowledge("Only in the live store.")

        await service.restore(backup.backup_id, overwrite=False)

        assert await _knowledge(manager) == ["Kept in the backup.", "Only in the live store."]
    assert [b.backup_id for b in store.list_backups()] == [backup.backup_id]


@pytest.mark.parametrize("failure", [SnapshotError("Restore incomplete: semantic (1 of 2)"), RuntimeError("qdrant down")])
async def test_failed_overwrite_restore_points_to_the_safety_copy_that_holds_the_previous_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryBackupService(manager, store)
        await manager.add_knowledge("Kept in the backup.")
        backup = await service.create()
        await manager.add_knowledge("Only in the live store.")

        async def failing_apply(*_args: object, **_kwargs: object) -> dict[str, int]:
            raise failure

        monkeypatch.setattr(service_module, "apply_snapshot", failing_apply)

        with pytest.raises(SnapshotError) as raised:
            await service.restore(backup.backup_id, overwrite=True)

    safety = next(b for b in store.list_backups() if b.description == PRE_RESTORE_DESCRIPTION)
    assert safety.backup_id in str(raised.value)
    assert "qdrant" not in str(raised.value)
    assert safety.memory_count == 2


async def test_restoring_an_unknown_or_corrupt_backup_leaves_memories_and_backups_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryBackupService(manager, store)
        await manager.add_knowledge("Live memory.")
        backup = await service.create()
        (tmp_path / "backups" / backup.backup_id / "snapshot.json.gz").write_bytes(b"damaged")

        with pytest.raises(BackupNotFoundError):
            await service.restore("memory_20260101_000000_abcdef12", overwrite=True)
        with pytest.raises(SnapshotError, match="corrupt"):
            await service.restore(backup.backup_id, overwrite=True)

        assert await _knowledge(manager) == ["Live memory."]
    assert [b.backup_id for b in store.list_backups()] == [backup.backup_id]


async def test_create_saves_nothing_when_the_capture_is_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = VolumeBackupStore(tmp_path / "backups")
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        await manager.add_knowledge("Live memory.")
        real_export = manager.export_all

        async def export_without_semantic() -> dict[str, list[dict[str, object]]]:
            exported = await real_export()
            exported.pop("semantic")
            return exported

        monkeypatch.setattr(manager, "export_all", export_without_semantic)

        with pytest.raises(SnapshotError, match="incomplete"):
            await MemoryBackupService(manager, store).create()

    assert store.list_backups() == []
