"""
[POS] tests/api/memory/test_auto_recall_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.auto_recall_router
[OUTPUT] test_evaluate_casual_chat_suppressed, test_evaluate_write_preflight_and_sliding_dedup, test_clear_session_and_force_recall
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.auto_recall_router import (
    router as auto_recall_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting auto-recall router."""
    test_app = FastAPI()
    test_app.include_router(auto_recall_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_evaluate_casual_chat_suppressed(client: TestClient) -> None:
    """Verify that casual conversational input suppresses auto-recall with zero candidate injection."""
    payload = {
        "session_id": "sess-chat-001",
        "current_turn": 1,
        "query_text": "Hello, how are you today?",
        "raw_candidates": [
            {
                "memory_id": "mem_danger_01",
                "content": "Do not delete production tables",
                "initial_score": 0.85,
            }
        ],
    }

    resp = client.post("/api/memory/auto-recall/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert not data["triggered"]
    assert data["trigger_type"] == "none"
    assert data["candidates_pre_dedup"] == 1
    assert data["candidates_post_dedup"] == 0
    assert len(data["injected_candidates"]) == 0
    assert data["reranker_status"] == "reranker_skipped"


def test_evaluate_write_preflight_and_sliding_dedup(client: TestClient) -> None:
    """Verify write preflight trigger activates recall, and subsequent turn suppresses repeat injection."""
    session_id = "sess-write-99"
    cands = [
        {
            "memory_id": "mem_atomic_1",
            "content": "Always run dry-run before altering tables",
            "initial_score": 0.88,
        },
        {
            "memory_id": "mem_atomic_2",
            "content": "Check schema diff before migration",
            "initial_score": 0.75,
        },
    ]

    # Turn 1: Write preflight trigger via tool name
    turn1_payload = {
        "session_id": session_id,
        "current_turn": 1,
        "tool_name": "replace_file_content",
        "raw_candidates": cands,
    }
    resp1 = client.post("/api/memory/auto-recall/evaluate", json=turn1_payload)
    assert resp1.status_code == 200
    data1 = resp1.json()

    assert data1["triggered"]
    assert data1["trigger_type"] == "write_preflight"
    assert data1["candidates_post_dedup"] == 2
    assert len(data1["injected_candidates"]) == 2
    injected_ids = [c["memory_id"] for c in data1["injected_candidates"]]
    assert "mem_atomic_1" in injected_ids

    # Query sliding window stats
    stats_resp = client.get(f"/api/memory/auto-recall/stats/{session_id}")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["active_window_turns"] == 1
    assert stats["total_suppressed_id_count"] == 2

    # Turn 2: Immediate follow-up write tool in same session -> Dedup suppresses both!
    turn2_payload = {
        "session_id": session_id,
        "current_turn": 2,
        "tool_name": "write_to_file",
        "raw_candidates": cands,
    }
    resp2 = client.post("/api/memory/auto-recall/evaluate", json=turn2_payload)
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert data2["triggered"]
    assert data2["candidates_post_dedup"] == 0
    assert len(data2["injected_candidates"]) == 0
    assert "suppressed by 5-turn dedup window" in data2["audit_reason"]


def test_clear_session_and_force_recall(client: TestClient) -> None:
    """Verify session clearance purges suppression cache and force_recall asserts task_start trigger."""
    session_id = "sess-clear-77"
    cand = {
        "memory_id": "mem_isolated",
        "content": "Verify lock timeout on postgres",
        "initial_score": 0.9,
    }

    # Injected once
    client.post(
        "/api/memory/auto-recall/evaluate",
        json={
            "session_id": session_id,
            "current_turn": 1,
            "event_name": "task_start",
            "raw_candidates": [cand],
        },
    )

    # Verify suppressed immediately after
    resp_suppressed = client.post(
        "/api/memory/auto-recall/evaluate",
        json={
            "session_id": session_id,
            "current_turn": 2,
            "event_name": "task_start",
            "raw_candidates": [cand],
        },
    )
    assert resp_suppressed.json()["candidates_post_dedup"] == 0

    # Purge session sliding cache
    del_resp = client.delete(f"/api/memory/auto-recall/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["cleared"]

    # Now force_recall passes through successfully
    force_resp = client.post(
        "/api/memory/auto-recall/evaluate",
        json={
            "session_id": session_id,
            "current_turn": 3,
            "force_recall": True,
            "raw_candidates": [cand],
        },
    )
    assert force_resp.status_code == 200
    force_data = force_resp.json()
    assert force_data["triggered"]
    assert force_data["candidates_post_dedup"] == 1
    assert len(force_data["injected_candidates"]) == 1
