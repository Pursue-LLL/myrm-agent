"""API contract tests for command-center project_id filtering."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.command_center import (
    MemoryCommandCenterResponse,
    MemoryCommandGovernanceItem,
)


def _build_empty_snapshot() -> MemoryCommandCenterResponse:
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
                "supported_sources": [],
                "tracked_imports": 0,
                "unmapped_items": 0,
                "coverage_status": "not_tracked",
                "adapter_status": {},
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


def test_command_center_governance_item_schema_supports_conflict_pair() -> None:
    """Ensure governance schema natively supports conflict_pair and detailed diff fields."""
    item = MemoryCommandGovernanceItem(
        id="gov_1",
        kind="conflict_pair",
        target_kind="conflict_pair",
        title="Conflict: procedural",
        description="Diff between formatting rules",
        severity="warning",
        status="pending",
        created_at=datetime.now(UTC),
        available_actions=["approve", "reject", "merge", "edit"],
        existing_value="prettier",
        candidate_value="biome",
        confidence=0.30,
        conflict_reason="Mutually exclusive tool choices",
    )
    assert item.target_kind == "conflict_pair"
    assert item.existing_value == "prettier"
    assert item.candidate_value == "biome"
    assert item.confidence == 0.30
    assert "merge" in item.available_actions


def test_command_center_without_project_id(client: TestClient) -> None:
    """GET /command-center without project_id uses global scope."""
    snapshot = _build_empty_snapshot()
    with (
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "__init__",
            return_value=None,
        ) as mock_init,
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "build_snapshot",
            new=AsyncMock(return_value=snapshot),
        ),
    ):
        response = client.get("/api/v1/memory/command-center")

    assert response.status_code == 200
    mock_init.assert_called_once()
    _, kwargs = mock_init.call_args
    assert kwargs.get("project_id") is None


def test_command_center_with_project_id(client: TestClient) -> None:
    """GET /command-center?project_id=xxx passes project_id to service."""
    snapshot = _build_empty_snapshot()
    with (
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "__init__",
            return_value=None,
        ) as mock_init,
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "build_snapshot",
            new=AsyncMock(return_value=snapshot),
        ),
    ):
        response = client.get("/api/v1/memory/command-center?project_id=proj-abc-123")

    assert response.status_code == 200
    mock_init.assert_called_once()
    _, kwargs = mock_init.call_args
    assert kwargs["project_id"] == "proj-abc-123"


def test_command_center_empty_project_id_normalized_to_none(client: TestClient) -> None:
    """GET /command-center?project_id= normalizes empty string to None (global scope)."""
    snapshot = _build_empty_snapshot()
    with (
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "__init__",
            return_value=None,
        ) as mock_init,
        patch.object(
            command_center_operation.MemoryCommandCenterService,
            "build_snapshot",
            new=AsyncMock(return_value=snapshot),
        ),
    ):
        response = client.get("/api/v1/memory/command-center?project_id=")

    assert response.status_code == 200
    mock_init.assert_called_once()
    _, kwargs = mock_init.call_args
    assert kwargs.get("project_id") is None
