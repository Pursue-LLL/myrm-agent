"""Unit tests for Mixed Fleet Local Brain and Remote Executor API (Item 47).

[INPUT]
- app.api.agents.mixed_fleet_router.router
- app.services.agent.mixed_fleet_service.MixedFleetService

[OUTPUT]
- Pytest test cases validating preset spec retrieval, fleet snapshot, dispatching
  from Local Brain, syncing from Remote Executor, completion, failure, and 503 offline gating.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_mixed_fleet_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.mixed_fleet_router import (
    get_mixed_fleet_service,
)
from app.api.agents.mixed_fleet_router import (
    router as mixed_fleet_router,
)
from app.services.agent.mixed_fleet_service import (
    MixedFleetService,
)


@pytest.fixture
def fleet_service() -> MixedFleetService:
    return MixedFleetService()


@pytest.fixture
def client(
    fleet_service: MixedFleetService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(mixed_fleet_router)
    app.dependency_overrides[get_mixed_fleet_service] = lambda: fleet_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_mixed_fleet_preset_spec_api(client: TestClient) -> None:
    resp = client.get("/agents/mixed-fleet/preset")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["preset_id"] == "preset-mixed-fleet-v1"
    assert len(data["local_capabilities"]) >= 3
    assert len(data["remote_capabilities"]) >= 3


def test_fleet_snapshot_and_dispatch_api(client: TestClient) -> None:
    chat_id = "test_mixed_chat_1"

    # 1. Snapshot
    snap_resp = client.get(f"/chats/{chat_id}/mixed-fleet/snapshot")
    assert snap_resp.status_code == 200
    snap = snap_resp.json()["data"]
    assert snap["chat_id"] == chat_id
    assert snap["local_brain"]["role"] == "local_brain"
    assert snap["remote_executor"]["role"] == "remote_executor"
    assert snap["total_handoffs"] == 0

    # 2. Dispatch task
    dispatch_resp = client.post(
        f"/chats/{chat_id}/mixed-fleet/dispatch",
        json={
            "task_instruction": "Extract web data and compile market trends",
            "context_files": ["market_queries.json"],
        },
    )
    assert dispatch_resp.status_code == 200
    manifest = dispatch_resp.json()["data"]
    assert manifest["manifest_id"].startswith("mf-handoff-")
    assert manifest["execution_status"] == "dispatched"
    assert "market_queries.json" in manifest["handoff_markdown"]

    # 3. Snapshot updated
    refreshed_snap = client.get(f"/chats/{chat_id}/mixed-fleet/snapshot").json()["data"]
    assert refreshed_snap["total_handoffs"] == 1
    assert refreshed_snap["active_manifest"]["manifest_id"] == manifest["manifest_id"]


def test_sync_and_complete_api(client: TestClient) -> None:
    chat_id = "test_mixed_chat_2"

    # Dispatch
    manifest = client.post(
        f"/chats/{chat_id}/mixed-fleet/dispatch",
        json={"task_instruction": "Continuous benchmark runner"},
    ).json()["data"]
    manifest_id = manifest["manifest_id"]

    # Sync
    sync_resp = client.post(f"/chats/{chat_id}/mixed-fleet/{manifest_id}/sync")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["data"]["synced_at"] is not None

    # Complete
    complete_resp = client.post(
        f"/chats/{chat_id}/mixed-fleet/{manifest_id}/complete",
        json={"output_summary": "Processed 10,000 transactions without error"},
    )
    assert complete_resp.status_code == 200
    completed_data = complete_resp.json()["data"]
    assert completed_data["execution_status"] == "completed"
    assert completed_data["output_summary"] == "Processed 10,000 transactions without error"


def test_fail_api(client: TestClient) -> None:
    chat_id = "test_mixed_chat_3"

    manifest = client.post(
        f"/chats/{chat_id}/mixed-fleet/dispatch",
        json={"task_instruction": "Docker build job"},
    ).json()["data"]
    manifest_id = manifest["manifest_id"]

    fail_resp = client.post(
        f"/chats/{chat_id}/mixed-fleet/{manifest_id}/fail",
        json={"error_detail": "Docker daemon disconnected unexpectedly"},
    )
    assert fail_resp.status_code == 200
    failed_data = fail_resp.json()["data"]
    assert failed_data["execution_status"] == "failed"
    assert failed_data["error_detail"] == "Docker daemon disconnected unexpectedly"


def test_heartbeat_and_offline_dispatch_error_api(client: TestClient) -> None:
    chat_id = "test_mixed_chat_4"

    # Set remote executor offline
    hb_resp = client.post(
        f"/chats/{chat_id}/mixed-fleet/heartbeat",
        json={"role": "remote_executor", "is_online": False},
    )
    assert hb_resp.status_code == 200
    assert hb_resp.json()["data"]["is_online"] is False

    # Dispatch should now fail with 503 Service Unavailable
    err_resp = client.post(
        f"/chats/{chat_id}/mixed-fleet/dispatch",
        json={"task_instruction": "Should fail because remote is offline"},
    )
    assert err_resp.status_code == 503
    assert "currently offline" in err_resp.json()["detail"]
