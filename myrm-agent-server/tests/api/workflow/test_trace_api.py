"""
[POS] tests/api/workflow/test_trace_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.workflow.trace_router
[OUTPUT] test_get_workflow_trace_seed, test_get_workflow_trace_on_demand, test_replay_from_node_success, test_replay_from_node_not_found
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.workflow.trace_router import (
    router as workflow_trace_router,
)


@pytest.fixture
def client() -> TestClient:
    """Provide isolated TestClient fixture mounting workflow trace router."""
    test_app = FastAPI()
    test_app.include_router(workflow_trace_router, prefix="/api/v1")
    with TestClient(test_app) as test_client:
        yield test_client


def test_get_workflow_trace_seed(client: TestClient) -> None:
    """Verify that seeded 5-stage workflow trace returns full holographic snapshots."""
    resp = client.get("/api/v1/workflow/wf-autonomous-sec-audit-01/trace")
    assert resp.status_code == 200
    data = resp.json()

    assert data["workflow_id"] == "wf-autonomous-sec-audit-01"
    assert data["task_id"] == "task-sec-audit-20261013"
    assert data["current_stage"] == "closure"
    assert len(data["nodes"]) == 5
    assert data["total_tokens"] > 0
    assert data["total_duration_ms"] > 0

    # Verify node snapshot structure and four-dimensional validation scores
    first_node = data["nodes"][0]
    assert first_node["node_id"] == "node-1-intake"
    assert first_node["stage"] == "intake"
    assert first_node["status"] == "completed"
    assert "validation_scores" in first_node
    scores = first_node["validation_scores"]
    assert scores["completeness"] >= 0.9
    assert scores["accuracy"] >= 0.9
    assert scores["compliance"] == 1.0
    assert scores["relevance"] >= 0.9
    assert scores["composite_score"] >= 0.9
    assert len(first_node["identity_hash"]) > 0


def test_get_workflow_trace_on_demand(client: TestClient) -> None:
    """Verify on-demand workflow trace generation for unknown workflow IDs."""
    resp = client.get("/api/v1/workflow/wf-custom-run-888/trace")
    assert resp.status_code == 200
    data = resp.json()

    assert data["workflow_id"] == "wf-custom-run-888"
    assert len(data["nodes"]) >= 2
    assert data["total_tokens"] > 0


def test_replay_from_node_success(client: TestClient) -> None:
    """Verify breakpoint self-healing replay: parent nodes cached, target overridden, downstream cascaded."""
    replay_payload = {
        "workflow_id": "wf-autonomous-sec-audit-01",
        "node_id": "node-3-dispatch",
        "override_inputs": {
            "sandbox_mode": "strict_volume_mount",
            "concurrency": 4,
            "allocated_gpu": "nvidia-a100",
        },
        "steer_prompt": "提速并发调度，优先扫描高危认证端点",
    }

    resp = client.post("/api/v1/workflow/replay-from-node", json=replay_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["workflow_id"] == "wf-autonomous-sec-audit-01"
    assert data["replayed_from_node_id"] == "node-3-dispatch"
    assert data["status"] == "completed"
    assert len(data["replayed_nodes"]) == 5

    # Parent nodes (node-1, node-2) must remain unchanged
    assert data["replayed_nodes"][0]["node_id"] == "node-1-intake"
    assert data["replayed_nodes"][1]["node_id"] == "node-2-planning"

    # Replayed breakpoint node (node-3) should reflect overridden inputs and steer prompt
    replayed_node = data["replayed_nodes"][2]
    assert replayed_node["node_id"] == "node-3-dispatch"
    assert replayed_node["input_payload"]["concurrency"] == 4
    assert replayed_node["input_payload"]["allocated_gpu"] == "nvidia-a100"
    assert "断点重放引导" in replayed_node["prompt_excerpt"]

    # Downstream nodes (node-4, node-5) should be refreshed
    downstream_node = data["replayed_nodes"][3]
    assert downstream_node["node_id"] == "node-4-execution"
    assert "跟随刷新" in downstream_node["title"]


def test_replay_from_node_not_found(client: TestClient) -> None:
    """Verify that replaying from a non-existent node returns failed status with clear diagnostics."""
    replay_payload = {
        "workflow_id": "wf-autonomous-sec-audit-01",
        "node_id": "non-existent-node-999",
        "override_inputs": {},
    }

    resp = client.post("/api/v1/workflow/replay-from-node", json=replay_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "failed"
    assert "not found" in data["message"].lower()
