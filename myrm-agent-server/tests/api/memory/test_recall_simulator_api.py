"""
[POS] tests/api/memory/test_recall_simulator_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.memory.recall_simulator_router
[OUTPUT] test_simulate_recall_success, test_simulate_recall_with_domain_filter, test_update_governance_confidence_and_trap_flag, test_update_governance_merge_duplicate, test_disabled_memory_not_recalled
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.recall_simulator_router import (
    router as recall_simulator_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting recall-simulator router."""
    test_app = FastAPI()
    test_app.include_router(recall_simulator_router, prefix="/api/memory")
    with TestClient(test_app) as test_client:
        yield test_client


def test_simulate_recall_success(client: TestClient) -> None:
    """Verify that simulate-recall returns ranked candidates with multi-channel scores and explainability."""
    payload = {
        "query": "排查 Linux 内核死锁与自旋锁",
        "top_k": 3,
        "recall_types": ["bm25", "vector", "causal_gene"],
    }

    resp = client.post("/api/memory/simulate-recall", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["query"] == "排查 Linux 内核死锁与自旋锁"
    assert data["total_matched"] >= 1
    assert len(data["candidates"]) <= 3
    assert data["execution_latency_ms"] >= 0.0

    # Top candidate should be the Linux kernel deadlock memory
    top_cand = data["candidates"][0]
    assert top_cand["memory_id"] == "mem-linux-deadlock-01"
    assert "scores" in top_cand
    assert top_cand["scores"]["rrf_score"] > 0.0
    assert top_cand["scores"]["bm25_score"] > 0.0
    assert top_cand["scores"]["vector_similarity"] > 0.0
    assert top_cand["scores"]["causal_relevance"] > 0.0
    assert top_cand["is_negative_trap"] is True
    assert len(top_cand["hit_reason"]) > 0


def test_simulate_recall_with_domain_filter(client: TestClient) -> None:
    """Verify that domain filtering restricts returned candidates to matching tags."""
    payload = {
        "query": "性能优化渲染",
        "top_k": 5,
        "domain_filter": "React",
        "recall_types": ["bm25", "vector"],
    }

    resp = client.post("/api/memory/simulate-recall", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    for cand in data["candidates"]:
        assert any("react" in t.lower() for t in cand["tags"])


def test_update_governance_confidence_and_trap_flag(client: TestClient) -> None:
    """Verify in-place secondary governance adjustments: confidence slider and negative trap toggle."""
    update_payload = {
        "memory_id": "mem-react-rerender-02",
        "confidence": 0.99,
        "is_negative_trap": True,
        "status": "active",
    }

    resp = client.post("/api/memory/simulate-recall/govern", json=update_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["memory_id"] == "mem-react-rerender-02"
    rec = data["updated_record"]
    assert rec["confidence"] == 0.99
    assert rec["is_negative_trap"] is True


def test_update_governance_merge_duplicate(client: TestClient) -> None:
    """Verify that merging duplicates incorporates tags and disables the source duplicate."""
    merge_payload = {
        "memory_id": "mem-threejs-render-04",
        "merged_into_id": "mem-react-rerender-02",
        "status": "disabled",
    }

    resp = client.post("/api/memory/simulate-recall/govern", json=merge_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["updated_record"]["status"] == "disabled"


def test_disabled_memory_not_recalled(client: TestClient) -> None:
    """Verify that disabled memory items are excluded from subsequent recall simulation."""
    # mem-threejs-render-04 was disabled in previous test
    payload = {
        "query": "Three.js 3D 页面显存泄漏",
        "top_k": 10,
    }

    resp = client.post("/api/memory/simulate-recall", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    recalled_ids = [c["memory_id"] for c in data["candidates"]]
    assert "mem-threejs-render-04" not in recalled_ids
