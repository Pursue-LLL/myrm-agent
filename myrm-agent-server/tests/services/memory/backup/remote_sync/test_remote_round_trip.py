"""Remote (WebDAV/S3 shaped) backup: capture, upload, download and non-destructive restore.

[INPUT]
app.services.memory.backup.remote_sync.runner::run_remote_backup/restore_from_remote

[OUTPUT]
Remote round trip on real memory stores through an in-memory remote storage.

[POS]
Only the network transport is replaced; the snapshot capture, file format, upload retry,
temp-file hygiene and merge restore all run for real.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.services.memory.backup.remote_sync.runner import restore_from_remote, run_remote_backup
from app.services.memory.backup.snapshot import decode_snapshot
from tests.support.in_memory_remote_backup import InMemoryBackupStrategy
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

TAG = "1a2b3c4d"


async def _seed(manager: MemoryManager) -> None:
    await manager.add_knowledge("User prefers dark mode in every editor.")
    await manager.add_knowledge("The release checklist lives in docs/release.md.")
    await manager.add_event("Deployed v2 on Friday and rolled back.")
    await manager.add_rule("deploying", "run smoke tests first")
    await manager.set_profile_attribute("name", "Alice")


async def _contents(manager: MemoryManager) -> dict[str, list[str]]:
    return {
        memory_type.value: sorted(m.content for m in await manager.list_memories(memory_type, limit=100))
        for memory_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC, MemoryType.PROFILE)
    }


async def test_remote_backup_restores_into_a_fresh_device_and_is_safe_to_repeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = InMemoryBackupStrategy()
    async with (
        offline_memory_manager(tmp_path / "laptop", monkeypatch) as laptop,
        offline_memory_manager(tmp_path / "phone", monkeypatch) as phone,
    ):
        await _seed(laptop)

        backup = await run_remote_backup(laptop, remote, instance_tag=TAG, device_name="laptop", max_backups=5)

        assert backup.status == "ok"
        file_name = str(backup.file_name)
        assert file_name in remote._storage
        assert backup.size_bytes == len(remote._storage[file_name])
        uploaded = decode_snapshot(remote._storage[file_name])
        assert {name: len(items) for name, items in uploaded.memories.items()} == {
            "profile": 1,
            "procedural": 1,
            "semantic": 2,
            "episodic": 1,
        }

        restored = await restore_from_remote(phone, remote, file_name)
        after_first_restore = await _contents(phone)
        await restore_from_remote(phone, remote, file_name)

        assert restored.success is True
        assert restored.restored_count == 5
        assert after_first_restore == await _contents(laptop)
        assert await _contents(phone) == after_first_restore
        assert await phone.count_memories(MemoryType.PROCEDURAL) == 1


async def test_remote_restore_never_deletes_memories_the_device_already_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = InMemoryBackupStrategy()
    async with (
        offline_memory_manager(tmp_path / "laptop", monkeypatch) as laptop,
        offline_memory_manager(tmp_path / "phone", monkeypatch) as phone,
    ):
        await _seed(laptop)
        await phone.add_knowledge("Only the phone knows this fact.")
        backup = await run_remote_backup(laptop, remote, instance_tag=TAG, device_name="laptop")

        await restore_from_remote(phone, remote, str(backup.file_name))

        assert "Only the phone knows this fact." in (await _contents(phone))["semantic"]
        assert await phone.count_memories(MemoryType.SEMANTIC) == 3


async def test_remote_backup_uploads_nothing_when_the_snapshot_would_be_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = InMemoryBackupStrategy()
    async with offline_memory_manager(tmp_path / "laptop", monkeypatch) as laptop:
        await _seed(laptop)
        real_export = laptop.export_all

        async def export_without_semantic() -> dict[str, list[dict[str, object]]]:
            exported = await real_export()
            exported.pop("semantic")
            return exported

        monkeypatch.setattr(laptop, "export_all", export_without_semantic)

        result = await run_remote_backup(laptop, remote, instance_tag=TAG, device_name="laptop")

    assert result.status == "failed"
    assert result.error_code == "snapshot"
    assert "incomplete" in str(result.error)
    assert remote._storage == {}


async def test_remote_restore_reports_an_approval_queue_manager_instead_of_losing_the_memories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = InMemoryBackupStrategy()
    async with (
        offline_memory_manager(tmp_path / "laptop", monkeypatch) as laptop,
        offline_memory_manager(tmp_path / "phone", monkeypatch, approval_required=True) as phone,
    ):
        await _seed(laptop)
        backup = await run_remote_backup(laptop, remote, instance_tag=TAG, device_name="laptop")

        result = await restore_from_remote(phone, remote, str(backup.file_name))

        assert result.success is False
        assert "approval queue" in str(result.error)
        assert await phone.count_memories(MemoryType.SEMANTIC) == 0


async def test_remote_file_names_cannot_steer_where_the_download_lands_and_temp_files_are_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    remote = InMemoryBackupStrategy()
    async with (
        offline_memory_manager(tmp_path / "laptop", monkeypatch) as laptop,
        offline_memory_manager(tmp_path / "phone", monkeypatch) as phone,
    ):
        await _seed(laptop)
        backup = await run_remote_backup(laptop, remote, instance_tag=TAG, device_name="laptop")
        remote._storage["../../escape.json.gz"] = remote._storage[str(backup.file_name)]

        result = await restore_from_remote(phone, remote, "../../escape.json.gz")

        assert result.success is True
    assert not (tmp_path / "escape.json.gz").exists()
    assert not (scratch.parent / "escape.json.gz").exists()
    assert list(scratch.iterdir()) == []
