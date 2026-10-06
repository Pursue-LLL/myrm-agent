"""
[POS] tests/api/memory/test_memory_unload_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.unload_router
[OUTPUT] test_emergency_flush_endpoint_creates_snapshot, test_list_unfinalized_sessions_endpoint, test_acknowledge_session_endpoint, test_emergency_flush_validation_error

Unit test suite for desktop and WebUI graceful flush and unload finalize guard API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.unload_guard import UnloadGracefulFlushGuard
from starlette.testclient import TestClient

from app.api.memory.unload_router import router as memory_unload_router
from app.services.memory.memory_unload_service import (
    MemoryUnloadService,
    get_memory_unload_service,
)


@pytest.fixture
def unload_test_client() -> Generator[tuple[TestClient, Path], None, None]:
    """Provide isolated TestClient mounting memory unload guard router with a mock storage directory."""
    with tempfile.TemporaryDirectory() as td:
        storage_path = Path(td)
        guard = UnloadGracefulFlushGuard(storage_dir=storage_path)
        service = MemoryUnloadService(guard=guard)

        test_app = FastAPI()
        test_app.include_router(memory_unload_router, prefix="/api/memory")
        test_app.dependency_overrides[get_memory_unload_service] = lambda: service

        with TestClient(test_app) as client:
            yield client, storage_path


def test_emergency_flush_endpoint_creates_snapshot(
    unload_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/unload/flush stores zero-LLM memorandum snapshot and registers handoff."""
    client, storage_path = unload_test_client

    payload = {
        "session_id": "sess-browser-crash-101",
        "reason": "browser_unload",
        "active_goal": "Migrating SQLite schema to Postgres",
        "unsaved_notes": ["Remember to run migration script #4", "Check index on column user_id"],
        "recent_messages": [
            {"role": "user", "content": "Let's update the schema now"},
            {"role": "assistant", "content": "I am preparing the migration script"},
        ],
        "target_handoff_agent": "db_migrator_agent",
    }

    resp = client.post("/api/memory/unload/flush", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["success"] is True
    assert data["handoff_id"].startswith("handoff-")
    assert data["reason"] == "browser_unload"
    assert data["finalized_at"] > 0

    snapshot_file = Path(data["snapshot_path"])
    assert snapshot_file.exists()
    content = snapshot_file.read_text(encoding="utf-8")
    assert "# Emergency Handoff Memorandum" in content
    assert "Migrating SQLite schema to Postgres" in content
    assert "Remember to run migration script #4" in content


def test_list_unfinalized_sessions_endpoint(
    unload_test_client: tuple[TestClient, Path],
) -> None:
    """Verify GET /api/memory/unload/unfinalized returns pending unfinalized sessions on startup."""
    client, _ = unload_test_client

    # Initially empty
    resp_init = client.get("/api/memory/unload/unfinalized")
    assert resp_init.status_code == 200
    assert resp_init.json()["unfinalized_sessions"] == []

    # Create two emergency unloads
    client.post(
        "/api/memory/unload/flush",
        json={
            "session_id": "sess-alpha",
            "reason": "window_close_requested",
            "active_goal": "Goal Alpha",
            "unsaved_notes": ["Note Alpha"],
            "recent_messages": [],
        },
    )
    client.post(
        "/api/memory/unload/flush",
        json={
            "session_id": "sess-beta",
            "reason": "crash_prevention",
            "active_goal": "Goal Beta",
            "unsaved_notes": [],
            "recent_messages": [],
        },
    )

    resp_list = client.get("/api/memory/unload/unfinalized")
    assert resp_list.status_code == 200
    sessions = resp_list.json()["unfinalized_sessions"]
    assert len(sessions) == 2

    session_ids = {s["session_id"] for s in sessions}
    assert "sess-alpha" in session_ids
    assert "sess-beta" in session_ids

    for s in sessions:
        assert s["status"] == "pending"


def test_acknowledge_session_endpoint(
    unload_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/unload/acknowledge marks handoff as claimed."""
    client, _ = unload_test_client

    # 1. Trigger flush
    client.post(
        "/api/memory/unload/flush",
        json={
            "session_id": "sess-ack-test",
            "reason": "browser_unload",
            "active_goal": "Goal Ack",
            "unsaved_notes": [],
            "recent_messages": [],
        },
    )

    # 2. Acknowledge session
    ack_resp = client.post(
        "/api/memory/unload/acknowledge",
        json={"session_id": "sess-ack-test"},
    )
    assert ack_resp.status_code == 200
    assert ack_resp.json()["success"] is True
    assert ack_resp.json()["session_id"] == "sess-ack-test"

    # 3. Verify no longer pending in unfinalized list
    list_resp = client.get("/api/memory/unload/unfinalized")
    assert list_resp.status_code == 200
    assert list_resp.json()["unfinalized_sessions"] == []


def test_emergency_flush_validation_error(
    unload_test_client: tuple[TestClient, Path],
) -> None:
    """Verify POST /api/memory/unload/flush rejects requests missing required fields."""
    client, _ = unload_test_client

    # Missing session_id
    resp = client.post("/api/memory/unload/flush", json={"reason": "browser_unload"})
    assert resp.status_code == 422
