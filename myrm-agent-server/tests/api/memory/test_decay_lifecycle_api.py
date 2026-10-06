"""Unit tests for Ebbinghaus memory decay and tiered storage lifecycle REST APIs.

[INPUT]
- TestClient and mock payloads for decay registration, evaluation, reranking, and revival.

[OUTPUT]
- Pytest cases validating /api/memory/lifecycle/ endpoints.

[POS]
- tests.api.memory.test_decay_lifecycle_api
"""

import time

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.decay_lifecycle_router import (
    router as decay_lifecycle_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting decay lifecycle router."""
    test_app = FastAPI()
    test_app.include_router(decay_lifecycle_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_register_and_evaluate_lifecycle_api(client: TestClient) -> None:
    """Verify POST /register and POST /evaluate lifecycle endpoints."""
    t0 = time.time()

    # Register fresh active memory
    reg_resp_1 = client.post(
        "/api/memory/lifecycle/register",
        json={
            "memory_id": "mem-api-active",
            "content": "User prefers concise answers",
            "importance": 0.9,
            "pinned": True,
            "created_at": t0,
        },
    )
    assert reg_resp_1.status_code == 200
    data_1 = reg_resp_1.json()
    assert data_1["memory_id"] == "mem-api-active"
    assert data_1["initial_tier"] == "HOT"
    assert data_1["pinned"] is True

    # Register stale memory created 60 days ago
    t_old = t0 - 60 * 86400.0
    reg_resp_2 = client.post(
        "/api/memory/lifecycle/register",
        json={
            "memory_id": "mem-api-stale",
            "content": "Temporary test token",
            "importance": 0.3,
            "pinned": False,
            "created_at": t_old,
        },
    )
    assert reg_resp_2.status_code == 200

    # Evaluate lifecycle migrations
    eval_resp = client.post(
        "/api/memory/lifecycle/evaluate",
        json={"current_time": t0},
    )
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_evaluated"] >= 2
    assert eval_data["hot_count"] >= 1


def test_rerank_candidates_api(client: TestClient) -> None:
    """Verify POST /rerank combines similarity with Ebbinghaus decay score."""
    t0 = time.time()

    # Register memories
    client.post(
        "/api/memory/lifecycle/register",
        json={"memory_id": "mem-fresh", "content": "Recent style guide", "importance": 0.95, "created_at": t0},
    )
    client.post(
        "/api/memory/lifecycle/register",
        json={
            "memory_id": "mem-ancient",
            "content": "Ancient snippet",
            "importance": 0.2,
            "created_at": t0 - 90 * 86400.0,
        },
    )

    rerank_payload = {
        "candidates": [
            {"memory_id": "mem-ancient", "content": "Ancient snippet", "base_similarity": 0.90},
            {"memory_id": "mem-fresh", "content": "Recent style guide", "base_similarity": 0.85},
        ],
        "decay_weight": 0.4,
        "exclude_cold": False,
        "current_time": t0,
    }

    resp = client.post("/api/memory/lifecycle/rerank", json=rerank_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_returned"] == 2
    assert data["items"][0]["memory_id"] == "mem-fresh"
    assert "decay_score" in data["items"][0]
    assert "final_score" in data["items"][0]


def test_revive_and_export_cold_archive_api(client: TestClient) -> None:
    """Verify GET /cold-archive and POST /revive endpoints."""
    t0 = time.time()
    t_old = t0 - 80 * 86400.0

    # Register memory and evaluate into cold tier
    client.post(
        "/api/memory/lifecycle/register",
        json={"memory_id": "mem-to-archive", "content": "Old archive item", "importance": 0.2, "created_at": t_old},
    )
    client.post("/api/memory/lifecycle/evaluate", json={"current_time": t0})

    # Export cold archive
    archive_resp = client.get("/api/memory/lifecycle/cold-archive")
    assert archive_resp.status_code == 200
    archive_data = archive_resp.json()
    assert archive_data["total_archived"] >= 1
    assert any(r["memory_id"] == "mem-to-archive" for r in archive_data["records"])

    # Revive cold memory
    revive_resp = client.post(
        "/api/memory/lifecycle/revive",
        json={"memory_id": "mem-to-archive", "boost_importance": 0.95},
    )
    assert revive_resp.status_code == 200
    revive_data = revive_resp.json()
    assert revive_data["memory_id"] == "mem-to-archive"
    assert revive_data["new_tier"] == "HOT"
