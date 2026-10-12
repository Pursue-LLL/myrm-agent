"""Unit tests for Snapshot Lag Aware Memory Freshness API (Item 157).

[INPUT]
- FastAPI TestClient, snapshot init, write delta records, status query, and disk hint endpoints.

[OUTPUT]
- Asserts verifying /snapshot-freshness/init, /record-write, /status, /hint, /delta-patch, and /reset endpoints.

[POS]
- Server-side test suite for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.snapshot_freshness_router import (
    router as snapshot_freshness_router,
)

app = FastAPI()
app.include_router(snapshot_freshness_router)
client = TestClient(app)


def test_init_session_snapshot_api() -> None:
    session_id = "test_sess_init_01"
    init_payload = {
        "session_id": session_id,
        "initial_content": "User prefers concise answers",
        "items_count": 3,
    }
    resp = client.post("/snapshot-freshness/init", json=init_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["digest"].startswith("snap_")
    assert data["initial_items_count"] == 3


def test_record_write_api() -> None:
    session_id = "test_sess_write_02"
    client.post(
        "/snapshot-freshness/init",
        json={"session_id": session_id, "initial_content": "init", "items_count": 1},
    )

    write_payload = {
        "session_id": session_id,
        "key": "deploy_target",
        "content": "Production AWS us-east-1",
        "turn_index": 2,
        "action": "update",
    }
    resp = client.post("/snapshot-freshness/record-write", json=write_payload)
    assert resp.status_code == 200
    state = resp.json()
    assert state["session_id"] == session_id
    assert state["is_dirty"] is True
    assert len(state["deltas"]) == 1
    assert state["deltas"][0]["key"] == "deploy_target"
    assert state["deltas"][0]["content"] == "Production AWS us-east-1"


def test_get_freshness_state_api() -> None:
    session_id = "test_sess_status_03"
    client.post(
        "/snapshot-freshness/init",
        json={"session_id": session_id, "initial_content": "k=v", "items_count": 1},
    )
    resp = client.get(f"/snapshot-freshness/status/{session_id}")
    assert resp.status_code == 200
    state = resp.json()
    assert state["session_id"] == session_id
    assert state["is_dirty"] is False
    assert len(state["deltas"]) == 0


def test_get_disk_read_hint_api() -> None:
    session_id = "test_sess_hint_04"
    client.post(
        "/snapshot-freshness/init",
        json={"session_id": session_id, "initial_content": "base", "items_count": 1},
    )

    # 1. Clean snapshot hint
    hint_clean = client.get(f"/snapshot-freshness/hint/{session_id}").json()
    assert hint_clean["is_dirty"] is False
    assert "完全一致" in hint_clean["hint_message"]
    assert len(hint_clean["affected_keys"]) == 0

    # 2. Mutate state
    client.post(
        "/snapshot-freshness/record-write",
        json={
            "session_id": session_id,
            "key": "auth_token",
            "content": "Bearer xyz",
            "turn_index": 1,
            "action": "update",
        },
    )

    # 3. Dirty snapshot hint with verification guidance
    hint_dirty = client.get(f"/snapshot-freshness/hint/{session_id}").json()
    assert hint_dirty["is_dirty"] is True
    assert "记忆快照感知契约" in hint_dirty["hint_message"]
    assert "auth_token" in hint_dirty["affected_keys"]


def test_get_delta_patch_and_reset_api() -> None:
    session_id = "test_sess_patch_05"
    client.post(
        "/snapshot-freshness/init",
        json={"session_id": session_id, "initial_content": "base", "items_count": 1},
    )
    client.post(
        "/snapshot-freshness/record-write",
        json={
            "session_id": session_id,
            "key": "preferred_language",
            "content": "TypeScript",
            "turn_index": 3,
            "action": "update",
        },
    )

    # Render patch
    patch_resp = client.get(f"/snapshot-freshness/delta-patch/{session_id}")
    assert patch_resp.status_code == 200
    patch = patch_resp.json()
    assert "SESSION MEMORY DELTA PATCH" in patch["header"]
    assert len(patch["patches"]) == 1
    assert "preferred_language" in patch["formatted_block"]

    # Reset
    reset_resp = client.post(f"/snapshot-freshness/reset/{session_id}")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"

    # Status after reset is fresh
    state_after = client.get(f"/snapshot-freshness/status/{session_id}").json()
    assert state_after["is_dirty"] is False
    assert len(state_after["deltas"]) == 0
