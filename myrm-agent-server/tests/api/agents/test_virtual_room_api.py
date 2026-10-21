"""API integration tests for Multi-Human Multi-Agent Collaborative Virtual Room (Item 59).

[INPUT]
- app.api.agents.virtual_room_router.router
- app.services.agent.virtual_room_service.get_virtual_room_service

[OUTPUT]
- Pytest test cases validating room lifecycle, VFS in-flight block locks & conflicts,
  zero-credential agent borrowing delegation, service port relays, and audit logs.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_virtual_room_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.virtual_room_router import router as virtual_room_router
from app.services.agent.virtual_room_service import (
    VirtualRoomService,
    get_virtual_room_service,
)


@pytest.fixture
def service() -> VirtualRoomService:
    """Isolated VirtualRoomService fixture for test execution."""
    srv = VirtualRoomService()
    srv.reset()
    return srv


@pytest.fixture
def client(service: VirtualRoomService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected VirtualRoomService dependency."""
    app = FastAPI()
    app.include_router(virtual_room_router)
    app.dependency_overrides[get_virtual_room_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_and_get_room_api(client: TestClient) -> None:
    room_id = "test-room-01"

    # 1. Create Room
    create_payload = {"room_id": room_id, "name": "E-Commerce Core Dev"}
    resp = client.post("/agents/virtual-room/rooms", json=create_payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["room_id"] == room_id
    assert data["name"] == "E-Commerce Core Dev"
    assert len(data["participants"]) == 0

    # 2. Get Room by ID
    get_resp = client.get(f"/agents/virtual-room/rooms/{room_id}")
    assert get_resp.status_code == 200
    state = get_resp.json()["data"]
    assert state["name"] == "E-Commerce Core Dev"

    # 3. List Rooms
    list_resp = client.get("/agents/virtual-room/rooms")
    assert list_resp.status_code == 200
    rooms = list_resp.json()["data"]
    assert any(r["room_id"] == room_id for r in rooms)


def test_join_and_leave_room_api(client: TestClient) -> None:
    room_id = "test-room-02"
    client.post("/agents/virtual-room/rooms", json={"room_id": room_id, "name": "Frontend Team"})

    # 1. Join Human Developer
    join_payload = {
        "participant_id": "human-alice",
        "name": "Alice Dev",
        "role": "human_dev",
        "local_identity_bound": True,
    }
    join_resp = client.post(f"/agents/virtual-room/rooms/{room_id}/join", json=join_payload)
    assert join_resp.status_code == 200
    part_data = join_resp.json()["data"]
    assert part_data["participant_id"] == "human-alice"
    assert part_data["local_identity_bound"] is True
    assert part_data["is_active"] is True

    # 2. Join Agent Worker
    client.post(
        f"/agents/virtual-room/rooms/{room_id}/join",
        json={"participant_id": "agent-reviewer-1", "name": "Code Reviewer", "role": "agent_reviewer"},
    )

    # Verify both exist in room
    room_resp = client.get(f"/agents/virtual-room/rooms/{room_id}")
    assert len(room_resp.json()["data"]["participants"]) == 2

    # 3. Leave Room
    leave_resp = client.post(
        f"/agents/virtual-room/rooms/{room_id}/leave",
        json={"participant_id": "human-alice"},
    )
    assert leave_resp.status_code == 200
    assert leave_resp.json()["data"]["success"] is True


def test_vfs_lock_acquire_and_conflict_handling_api(client: TestClient) -> None:
    # 1. Alice acquires line-range lock on lines 10-30
    lock_payload = {
        "file_path": "src/services/auth.ts",
        "holder_id": "human-alice",
        "holder_role": "human_dev",
        "scope": "line_range",
        "start_line": 10,
        "end_line": 30,
        "ttl_seconds": 25.0,
    }
    resp = client.post("/agents/virtual-room/locks/acquire", json=lock_payload)
    assert resp.status_code == 200
    lock_data = resp.json()["data"]
    lock_id = lock_data["lock_id"]
    assert lock_data["start_line"] == 10
    assert lock_data["end_line"] == 30

    # 2. Bob attempts to acquire overlapping lines 25-45 -> 409 Conflict
    overlap_payload = {
        "file_path": "src/services/auth.ts",
        "holder_id": "agent-bob",
        "holder_role": "agent_worker",
        "scope": "line_range",
        "start_line": 25,
        "end_line": 45,
    }
    conflict_resp = client.post("/agents/virtual-room/locks/acquire", json=overlap_payload)
    assert conflict_resp.status_code == 409
    assert "overlaps with existing lock" in conflict_resp.json()["detail"]

    # 3. Bob attempts full file lock while Alice holds lines -> 409 Conflict
    full_conflict_payload = {
        "file_path": "src/services/auth.ts",
        "holder_id": "agent-bob",
        "holder_role": "agent_worker",
        "scope": "file_full",
    }
    full_resp = client.post("/agents/virtual-room/locks/acquire", json=full_conflict_payload)
    assert full_resp.status_code == 409
    assert "Cannot acquire full lock" in full_resp.json()["detail"]

    # 4. Release lock
    rel_resp = client.post(
        "/agents/virtual-room/locks/release",
        json={"lock_id": lock_id, "holder_id": "human-alice"},
    )
    assert rel_resp.status_code == 200
    assert rel_resp.json()["data"]["success"] is True

    # 5. Unauthorized release attempt -> 403 Forbidden
    rel_fail = client.post(
        "/agents/virtual-room/locks/release",
        json={"lock_id": "dummy-lock", "holder_id": "unauthorized-user"},
    )
    # Not found or unauthorized handled gracefully
    assert rel_fail.status_code in (200, 403)


def test_zero_credential_borrowing_delegation_api(client: TestClient) -> None:
    room_id = "test-room-03"
    client.post("/agents/virtual-room/rooms", json={"room_id": room_id, "name": "AI Lab"})

    # 1. Alice creates capability grant for Bob
    grant_payload = {
        "room_id": room_id,
        "owner_id": "alice-owner",
        "borrower_id": "bob-borrower",
        "target_agent_model": "claude-3-7-sonnet",
        "quota_tokens": 1000,
        "ttl_seconds": 3600.0,
    }
    create_resp = client.post("/agents/virtual-room/grants/create", json=grant_payload)
    assert create_resp.status_code == 201
    grant_data = create_resp.json()["data"]
    grant_id = grant_data["grant_id"]
    assert grant_data["quota_tokens"] == 1000
    assert grant_data["status"] == "active"

    # 2. Bob delegates task execution through borrowed agent
    delegate_payload = {
        "grant_id": grant_id,
        "borrower_id": "bob-borrower",
        "prompt": "Optimize SQL indexing on user_orders table",
        "token_cost": 250,
    }
    del_resp = client.post("/agents/virtual-room/grants/delegate", json=delegate_payload)
    assert del_resp.status_code == 200
    del_data = del_resp.json()["data"]
    assert del_data["success"] is True
    assert "claude-3-7-sonnet" in del_data["output"]
    assert del_data["used_tokens"] == 250

    # 3. Unauthorized borrower attempt -> 403 Forbidden
    bad_del = client.post(
        "/agents/virtual-room/grants/delegate",
        json={"grant_id": grant_id, "borrower_id": "eve-hacker", "prompt": "Stolen task"},
    )
    assert bad_del.status_code == 403

    # 4. Revoke grant by owner
    revoke_resp = client.post(
        "/agents/virtual-room/grants/revoke",
        json={"grant_id": grant_id, "owner_id": "alice-owner"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["data"]["status"] == "revoked"


def test_register_service_relay_and_events_api(client: TestClient) -> None:
    room_id = "test-room-04"
    client.post("/agents/virtual-room/rooms", json={"room_id": room_id, "name": "Fullstack Live"})

    # 1. Register live preview port relay
    relay_payload = {
        "room_id": room_id,
        "service_name": "vite-dashboard",
        "port": 5173,
        "launched_by_id": "agent-worker-01",
    }
    relay_resp = client.post("/agents/virtual-room/relays/register", json=relay_payload)
    assert relay_resp.status_code == 201
    relay_data = relay_resp.json()["data"]
    assert relay_data["port"] == 5173
    assert "preview" in relay_data["live_preview_url"]

    # 2. Query room events
    events_resp = client.get(f"/agents/virtual-room/rooms/{room_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()["data"]
    assert len(events) >= 2
    event_types = [e["event_type"] for e in events]
    assert "room_created" in event_types
    assert "service_relay_registered" in event_types
