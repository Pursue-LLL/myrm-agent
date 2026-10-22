"""Unit tests for Cross-Surface Agent Activity Conversation Bridge API (Item 49).

[INPUT]
- app.api.agents.cross_surface_bridge_router.router
- app.services.agent.cross_surface_bridge_service.CrossSurfaceBridgeService

[OUTPUT]
- Pytest test cases validating single activity ingress, batch ingress,
  bounded projection query, stale presence pruning, and session ledger reset.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_cross_surface_bridge_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.cross_surface_bridge_router import (
    get_service,
)
from app.api.agents.cross_surface_bridge_router import (
    router as cross_surface_bridge_router,
)
from app.services.agent.cross_surface_bridge_service import (
    CrossSurfaceBridgeService,
)


@pytest.fixture
def service() -> CrossSurfaceBridgeService:
    return CrossSurfaceBridgeService(max_recent_items=20)


@pytest.fixture
def client(
    service: CrossSurfaceBridgeService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(cross_surface_bridge_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ingress_single_activity_api(client: TestClient) -> None:
    chat_id = "test-chat-bridge-001"
    resp = client.post(
        f"/chats/{chat_id}/activity-bridge/ingress",
        json={
            "activity_id": "act-tauri-1",
            "session_key": "tauri-local-thread",
            "source_surface": "tauri_desktop",
            "agent_id": "desktop-agent-v1",
            "activity_kind": "turn_start",
            "preview_text": "Local file tree indexed",
            "metadata": {"items_indexed": 120},
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["chat_id"] == chat_id
    assert data["total_ingressed_activities"] == 1
    assert len(data["active_presences"]) == 1
    presence = data["active_presences"][0]
    assert presence["session_key"] == "tauri-local-thread"
    assert presence["source_surface"] == "tauri_desktop"
    assert presence["status"] == "active"
    assert presence["recent_activities_count"] == 1
    assert len(data["bounded_recent_activities"]) == 1


def test_ingress_batch_activities_api(client: TestClient) -> None:
    chat_id = "test-chat-bridge-002"
    resp = client.post(
        f"/chats/{chat_id}/activity-bridge/ingress-batch",
        json={
            "activities": [
                {
                    "activity_id": f"act-cli-{i}",
                    "session_key": "cli-terminal-session",
                    "source_surface": "cli_tool",
                    "agent_id": "cli-worker",
                    "activity_kind": "tool_call",
                    "preview_text": f"Running command bash #{i}",
                }
                for i in range(3)
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_ingressed_activities"] == 3
    assert len(data["bounded_recent_activities"]) == 3
    assert data["active_presences"][0]["recent_activities_count"] == 3


def test_get_projection_api(client: TestClient) -> None:
    chat_id = "test-chat-bridge-003"
    client.post(
        f"/chats/{chat_id}/activity-bridge/ingress",
        json={
            "activity_id": "act-cron-1",
            "session_key": "cron-daily-nightly",
            "source_surface": "cron_job",
            "agent_id": "nightly-runner",
            "activity_kind": "thinking_pulse",
            "preview_text": "Compacting workspace backups",
        },
    )

    resp = client.get(f"/chats/{chat_id}/activity-bridge/projection")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total_ingressed_activities"] == 1
    assert data["active_presences"][0]["source_surface"] == "cron_job"
    assert len(data["bounded_recent_activities"]) == 1


def test_prune_stale_presences_api(client: TestClient) -> None:
    chat_id = "test-chat-bridge-004"
    client.post(
        f"/chats/{chat_id}/activity-bridge/ingress",
        json={
            "activity_id": "act-clone-1",
            "session_key": "office-clone-hk",
            "source_surface": "remote_office_clone",
            "agent_id": "remote-office-agent",
            "activity_kind": "heartbeat",
            "preview_text": "Office clone heartbeat ping",
        },
    )

    resp = client.post(
        f"/chats/{chat_id}/activity-bridge/prune-stale",
        json={"max_idle_seconds": 600.0},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "pruned_count" in data
    assert "updated_snapshot" in data


def test_reset_projection_api(client: TestClient) -> None:
    chat_id = "test-chat-bridge-005"
    client.post(
        f"/chats/{chat_id}/activity-bridge/ingress",
        json={
            "activity_id": "act-temp",
            "session_key": "session-to-clear",
            "source_surface": "cli_tool",
            "agent_id": "temp-agent",
            "activity_kind": "tool_result",
            "preview_text": "Transient task completed",
        },
    )

    reset_resp = client.post(f"/chats/{chat_id}/activity-bridge/reset")
    assert reset_resp.status_code == 200
    data = reset_resp.json()["data"]
    assert data["total_ingressed_activities"] == 0
    assert len(data["active_presences"]) == 0
    assert len(data["bounded_recent_activities"]) == 0
