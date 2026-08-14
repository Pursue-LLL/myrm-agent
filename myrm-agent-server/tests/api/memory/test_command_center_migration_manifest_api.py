"""API contract tests for command-center migration manifest fields."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.command_center import MemoryCommandCenterResponse


def _build_snapshot(*, authoritative: bool) -> MemoryCommandCenterResponse:
    now = datetime.now(UTC)
    return MemoryCommandCenterResponse.model_validate(
        {
            "generated_at": now,
            "overview": {
                "total_memories": 0,
                "by_type": {},
                "pending_memories": 0,
                "pending_shared_proposals": 0,
                "active_shared_contexts": 0,
                "health_status": "unknown",
                "deploy_mode": "local",
            },
            "spaces": [],
            "governance": [],
            "health": {"status": "unknown"},
            "timeline": [],
            "migration": {
                "supported_sources": ["hermes", "openclaw", "claude", "codex", "chatgpt"],
                "source_manifest": [
                    {
                        "id": "hermes",
                        "display_name": "Hermes",
                        "import_source": "hermes",
                        "discover_modes": ["local_scan"],
                        "deep_link_enabled": True,
                    }
                ],
                "source_manifest_authoritative": authoritative,
                "tracked_imports": 0,
                "unmapped_items": 0,
                "coverage_status": "not_tracked",
                "adapter_status": {"hermes": "ready"},
            },
            "plane_summary": {
                "enabled": True,
                "content_visibility": "not_shared",
                "health_status": "unknown",
                "import_rollback_health_status": "ready",
                "event_count": 0,
                "failed_event_count": 0,
                "queue_backlog": 0,
                "storage_mode": "sqlite",
                "redaction_scope": "metadata_only",
                "sandbox_isolation": "local_or_per_user_sandbox",
            },
            "runtime": {
                "deploy_mode": "local",
                "storage_mode": "sqlite",
                "memory_base_path": "/tmp/memory",
                "relational_status": "available",
                "vector_status": "available",
                "vector_persistence": "persistent",
                "graph_status": "unavailable",
                "embedding_status": "custom",
                "control_plane_status": "not_used",
                "event_ledger_status": "available",
                "health_snapshot_status": "available",
                "supported_clients": ["local_web"],
            },
        }
    )


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/v1/memory")

    async def _fake_db():
        yield AsyncMock()

    async def _fake_manager():
        return AsyncMock()

    app.dependency_overrides[get_db_session] = _fake_db
    app.dependency_overrides[get_crud_memory_manager] = _fake_manager
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client
    app.dependency_overrides.clear()


def test_command_center_snapshot_exposes_authoritative_manifest_flag(client: TestClient) -> None:
    snapshot = _build_snapshot(authoritative=True)
    with patch.object(
        command_center_operation.MemoryCommandCenterService,
        "build_snapshot",
        new=AsyncMock(return_value=snapshot),
    ) as mock_build_snapshot:
        response = client.get("/api/v1/memory/command-center")

    assert response.status_code == 200
    data = response.json()
    assert data["migration"]["source_manifest_authoritative"] is True
    assert data["migration"]["source_manifest"][0]["id"] == "hermes"
    mock_build_snapshot.assert_awaited_once()
