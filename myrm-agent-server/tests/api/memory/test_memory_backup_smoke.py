"""HTTP flow of the memory backup routes on a real memory manager.

[INPUT]
app.api.memory.operations.backup::router
app.services.memory.backup (service, snapshot, volume store)

[OUTPUT]
create -> list -> restore -> delete through HTTP, and the response shapes the settings panel
relies on when a backup is missing or cannot be completed.

[POS]
Route-level contract of the backup panel. Routing, service and persistence are the real ones;
only the embedder (offline) and the volume root (a temporary directory) are redirected.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores

from app.api.memory.operations.backup import get_backup_store
from app.api.memory.router import router as memory_router
from app.api.memory.utils import get_crud_memory_manager
from app.services.memory.backup.service import PRE_RESTORE_DESCRIPTION
from app.services.memory.backup.volume_store import VolumeBackupStore
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class BackupApi:
    client: AsyncClient
    manager: MemoryManager
    store: VolumeBackupStore
    root: Path


@pytest.fixture
async def backup_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[BackupApi]:
    await clear_embedded_stores()
    root = tmp_path / "backups"
    store = VolumeBackupStore(root)
    app = FastAPI()
    app.include_router(memory_router, prefix="/memory")
    app.dependency_overrides[get_backup_store] = lambda: store
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        app.dependency_overrides[get_crud_memory_manager] = lambda: manager
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield BackupApi(client=client, manager=manager, store=store, root=root)
    await clear_embedded_stores()


async def _knowledge(manager: MemoryManager) -> list[str]:
    return sorted(m.content for m in await manager.list_memories(MemoryType.SEMANTIC, limit=100))


async def test_a_backup_can_be_created_listed_restored_and_deleted(backup_api: BackupApi) -> None:
    client, manager = backup_api.client, backup_api.manager
    await manager.add_knowledge("Kept in the backup.")
    await manager.add_rule("deploying", "run smoke tests first")

    created = await client.post("/memory/backup/create", json={"description": "nightly"})

    assert created.status_code == 200
    created_body = created.json()
    assert created_body["success"] is True
    assert created_body["error"] is None
    assert created_body["metadata"]["memory_count"] == 2
    assert created_body["metadata"]["description"] == "nightly"
    backup_id = created_body["backup_id"]
    assert created_body["metadata"]["backup_id"] == backup_id

    listed = (await client.get("/memory/backup/list")).json()
    assert listed["total"] == 1
    assert [b["backup_id"] for b in listed["backups"]] == [backup_id]

    await manager.add_knowledge("Added after the backup.")
    restored = await client.post("/memory/backup/restore", json={"backup_id": backup_id, "overwrite": True})

    assert restored.status_code == 200
    assert restored.json()["success"] is True
    assert restored.json()["restored_count"] == 2
    assert await _knowledge(manager) == ["Kept in the backup."]

    backups = (await client.get("/memory/backup/list")).json()["backups"]
    assert sorted(b["description"] or "" for b in backups) == sorted(["nightly", PRE_RESTORE_DESCRIPTION])

    deleted = await client.delete(f"/memory/backup/{backup_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"success": True}
    remaining = (await client.get("/memory/backup/list")).json()
    assert [b["description"] for b in remaining["backups"]] == [PRE_RESTORE_DESCRIPTION]


async def test_restore_without_overwrite_merges_into_what_is_already_there(backup_api: BackupApi) -> None:
    client, manager = backup_api.client, backup_api.manager
    await manager.add_knowledge("Kept in the backup.")
    backup_id = (await client.post("/memory/backup/create", json={})).json()["backup_id"]
    await manager.add_knowledge("Added after the backup.")

    restored = await client.post("/memory/backup/restore", json={"backup_id": backup_id, "overwrite": False})

    assert restored.json()["success"] is True
    assert await _knowledge(manager) == ["Added after the backup.", "Kept in the backup."]
    assert (await client.get("/memory/backup/list")).json()["total"] == 1


async def test_unknown_or_malformed_backup_ids_are_404_and_cost_nothing(backup_api: BackupApi) -> None:
    client, manager = backup_api.client, backup_api.manager
    await manager.add_knowledge("Must survive.")

    for backup_id in ("memory_20200101_000000_deadbeef", "../outside", "/etc"):
        response = await client.post("/memory/backup/restore", json={"backup_id": backup_id, "overwrite": True})
        assert response.status_code == 404, backup_id

    assert (await client.delete("/memory/backup/memory_20200101_000000_deadbeef")).status_code == 404
    assert await _knowledge(manager) == ["Must survive."]
    assert backup_api.store.list_backups() == []


async def test_an_incomplete_snapshot_is_reported_and_nothing_is_saved(
    backup_api: BackupApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, manager = backup_api.client, backup_api.manager
    await manager.add_knowledge("Would be lost.")
    real_export = manager.export_all

    async def export_without_semantic() -> dict[str, list[dict[str, object]]]:
        exported = await real_export()
        exported.pop("semantic")
        return exported

    monkeypatch.setattr(manager, "export_all", export_without_semantic)

    response = await client.post("/memory/backup/create", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["backup_id"] is None
    assert "incomplete" in body["error"]
    assert backup_api.store.list_backups() == []


async def test_a_corrupt_backup_file_fails_the_restore_without_touching_memories(backup_api: BackupApi) -> None:
    client, manager = backup_api.client, backup_api.manager
    await manager.add_knowledge("Must survive.")
    backup_id = (await client.post("/memory/backup/create", json={})).json()["backup_id"]
    (backup_api.root / backup_id / "snapshot.json.gz").write_bytes(b"not gzip at all")

    response = await client.post("/memory/backup/restore", json={"backup_id": backup_id, "overwrite": True})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["restored_count"] == 0
    assert "corrupt" in body["error"]
    assert await _knowledge(manager) == ["Must survive."]
    assert [b.backup_id for b in backup_api.store.list_backups()] == [backup_id]
