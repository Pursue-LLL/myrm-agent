"""API integration tests for Lightweight Fusen Shared State Sync (Item 63).

[INPUT]
- app.api.agents.fusen_router.router
- app.services.agent.fusen_service.FusenSharedStateService

[OUTPUT]
- Pytest test cases verifying Fusen sticky-note posting, resolution, filtering,
  blocker checks, and TTL cleanup endpoints.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_fusen_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.fusen_router import router as fusen_router
from app.services.agent.fusen_service import FusenSharedStateService


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory Fusen board state before each test."""
    FusenSharedStateService.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with fusen_router attached."""
    app = FastAPI()
    app.include_router(fusen_router)
    return TestClient(app)


def test_post_and_get_fusen_note_api(client: TestClient) -> None:
    """Test posting a sticky note and retrieving its details."""
    req_body = {
        "note_id": "fusen-test-01",
        "session_id": "sess-alpha-01",
        "author_agent_id": "worker-scout",
        "category": "ready_for_review",
        "tag": "ready_for_review: diff_auth",
        "content": "Added strict token rotation.",
        "metadata": {"lines_changed": "25"},
    }
    resp = client.post("/agents/fusen/notes", json=req_body)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["note_id"] == "fusen-test-01"
    assert data["session_id"] == "sess-alpha-01"
    assert data["author_agent_id"] == "worker-scout"
    assert data["category"] == "ready_for_review"
    assert data["tag"] == "ready_for_review: diff_auth"
    assert data["status"] == "active"
    assert data["metadata"]["lines_changed"] == "25"

    # Get note by ID
    get_resp = client.get("/agents/fusen/notes/fusen-test-01")
    assert get_resp.status_code == 200
    get_data = get_resp.json()["data"]
    assert get_data["note_id"] == "fusen-test-01"
    assert get_data["content"] == "Added strict token rotation."


def test_resolve_fusen_note_api(client: TestClient) -> None:
    """Test resolving an active sticky note."""
    client.post(
        "/agents/fusen/notes",
        json={
            "note_id": "fusen-blk-01",
            "session_id": "sess-beta",
            "author_agent_id": "worker-db",
            "category": "blocker",
            "tag": "blocked_by: migration_lock",
        },
    )

    resolve_resp = client.post(
        "/agents/fusen/notes/fusen-blk-01/resolve",
        json={"resolution_note": "Migration executed cleanly."},
    )
    assert resolve_resp.status_code == 200
    data = resolve_resp.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolution_note"] == "Migration executed cleanly."


def test_list_fusen_notes_filtered_api(client: TestClient) -> None:
    """Test querying notes by session, category, and tag_prefix."""
    client.post(
        "/agents/fusen/notes",
        json={
            "session_id": "sess-1",
            "author_agent_id": "worker-1",
            "category": "cache_hint",
            "tag": "cache_hit: docker_builder",
        },
    )
    client.post(
        "/agents/fusen/notes",
        json={
            "session_id": "sess-1",
            "author_agent_id": "worker-2",
            "category": "in_progress",
            "tag": "in_progress: lint_check",
        },
    )
    client.post(
        "/agents/fusen/notes",
        json={
            "session_id": "sess-2",
            "author_agent_id": "worker-3",
            "category": "cache_hint",
            "tag": "cache_hit: go_build_cache",
        },
    )

    # Filter by session_id
    res1 = client.get("/agents/fusen/notes?session_id=sess-1")
    assert len(res1.json()["data"]) == 2

    # Filter by category
    res2 = client.get("/agents/fusen/notes?category=cache_hint")
    assert len(res2.json()["data"]) == 2

    # Filter by tag_prefix
    res3 = client.get("/agents/fusen/notes?tag_prefix=in_progress:")
    assert len(res3.json()["data"]) == 1
    assert res3.json()["data"][0]["author_agent_id"] == "worker-2"


def test_check_blockers_api(client: TestClient) -> None:
    """Test rapid sub-millisecond blocker check endpoint."""
    # Initially 0 blockers
    init_resp = client.get("/agents/fusen/blockers?session_id=sess-gate")
    assert init_resp.status_code == 200
    assert init_resp.json()["data"]["is_blocked"] is False
    assert init_resp.json()["data"]["blocker_count"] == 0

    # Post a blocker
    client.post(
        "/agents/fusen/notes",
        json={
            "session_id": "sess-gate",
            "author_agent_id": "agent-gatekeeper",
            "category": "blocker",
            "tag": "blocked_by: third_party_rate_limit",
            "metadata": {"target_agent_id": "worker-api"},
        },
    )

    # Query for another agent (not blocked)
    resp_other = client.get("/agents/fusen/blockers?session_id=sess-gate&target_agent_id=worker-ui")
    assert resp_other.json()["data"]["is_blocked"] is False

    # Query for target agent (blocked)
    resp_target = client.get("/agents/fusen/blockers?session_id=sess-gate&target_agent_id=worker-api")
    assert resp_target.json()["data"]["is_blocked"] is True
    assert resp_target.json()["data"]["blocker_count"] == 1


def test_cleanup_expired_api(client: TestClient) -> None:
    """Test cleanup endpoint execution."""
    client.post(
        "/agents/fusen/notes",
        json={
            "session_id": "sess-temp",
            "author_agent_id": "worker-ephemeral",
            "category": "custom",
            "tag": "temp_note",
            "ttl_seconds": 3600.0,
        },
    )
    cleanup_resp = client.post("/agents/fusen/cleanup-expired")
    assert cleanup_resp.status_code == 200
    assert "pruned_count" in cleanup_resp.json()["data"]


def test_get_non_existent_note_404(client: TestClient) -> None:
    """Test retrieving non-existent note returns 404."""
    resp = client.get("/agents/fusen/notes/non-existent-id")
    assert resp.status_code == 404
