"""Smoke tests for memory backup and archival HTTP routes (auth + JSON shape).

Covers:
- GET /memory/backup/list — empty list
- POST /memory/backup/create — success path (manager mocked)
- POST /memory/backup/restore — success path (manager mocked)
- DELETE /memory/backup/{id} — success path (manager mocked)
- POST /memory/archival/auto — zero archived (typical dev DB)

Uses dependency overrides only (no external services).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory.archival import ArchivalResult
from myrm_agent_harness.toolkits.memory.backup import BackupMetadata, BackupResult, RestoreResult

from app.api.memory.router import router as memory_router
from app.api.memory.utils import get_crud_memory_manager, get_memory_manager


def _build_client(
    *,
    mock_full: MagicMock,
) -> TestClient:
    app = FastAPI()
    app.include_router(memory_router, prefix="/memory")

    async def mock_uid() -> str:
        return "test-user-smoke"

    mock_crud = MagicMock()
    mock_full.archive_memories_auto = AsyncMock(
        return_value=ArchivalResult(archived_count=0, candidates=[], duration_ms=1.0),
    )

    async def dep_crud() -> MagicMock:
        return mock_crud

    async def dep_full() -> MagicMock:
        return mock_full

    pass
    app.dependency_overrides[get_crud_memory_manager] = dep_crud
    app.dependency_overrides[get_memory_manager] = dep_full

    return TestClient(app)


@pytest.fixture
def memory_test_client() -> TestClient:
    mock_full = MagicMock()
    mock_full.list_backups = AsyncMock(return_value=[])
    return _build_client(mock_full=mock_full)


def test_backup_list_returns_empty_array(memory_test_client: TestClient) -> None:
    response = memory_test_client.get("/memory/backup/list")
    assert response.status_code == 200
    data = response.json()
    assert data["backups"] == []
    assert data["total"] == 0


def test_archival_auto_returns_json(memory_test_client: TestClient) -> None:
    response = memory_test_client.post("/memory/archival/auto")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["archived_count"] == 0
    assert "duration_ms" in data


def test_backup_create_restore_delete_json_shape() -> None:
    meta = BackupMetadata(
        backup_id="bk_smoke_1",
        created_at=datetime.now(UTC),
        memory_count=3,
        size_bytes=120,
        collections=["semantic_default"],
        description="smoke",
    )
    mock_full = MagicMock()
    mock_full.list_backups = AsyncMock(return_value=[])
    mock_full.create_backup = AsyncMock(
        return_value=BackupResult(success=True, metadata=meta, duration_ms=1.5, error=None),
    )
    mock_full.restore_backup = AsyncMock(
        return_value=RestoreResult(success=True, restored_count=3, duration_ms=2.0, error=None),
    )
    mock_full.delete_backup = AsyncMock(return_value=True)

    client = _build_client(mock_full=mock_full)

    create_res = client.post("/memory/backup/create", json={"description": "smoke"})
    assert create_res.status_code == 200
    cj = create_res.json()
    assert cj["success"] is True
    assert cj["backup_id"] == "bk_smoke_1"
    assert cj["metadata"]["memory_count"] == 3

    restore_res = client.post(
        "/memory/backup/restore",
        json={"backup_id": "bk_smoke_1", "overwrite": False},
    )
    assert restore_res.status_code == 200
    rj = restore_res.json()
    assert rj["success"] is True
    assert rj["restored_count"] == 3

    delete_res = client.delete("/memory/backup/bk_smoke_1")
    assert delete_res.status_code == 200
    assert delete_res.json()["success"] is True
