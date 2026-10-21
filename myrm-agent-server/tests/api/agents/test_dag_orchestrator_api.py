"""API integration tests for DAG Visual Orchestrator with Cold Resume and Bidirectional Feedback (Item 69).

[INPUT]
- app.api.agents.dag_orchestrator_router.router
- app.services.agent.dag_orchestrator_service.get_dag_orchestrator_service

[OUTPUT]
- Pytest assertions verifying natural language team planning, step advancement,
  cold resume from persistent checkpoints, and downstream cascade reject loopback.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_dag_orchestrator_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.dag_orchestrator_router import router as dag_orchestrator_router
from app.services.agent.dag_orchestrator_service import get_dag_orchestrator_service


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory DAGs and snapshots before each test."""
    service = get_dag_orchestrator_service()
    service.reset()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with dag_orchestrator_router attached."""
    app = FastAPI()
    app.include_router(dag_orchestrator_router)
    return TestClient(app)


def test_plan_dag_api(client: TestClient) -> None:
    """Test generating a multi-agent DAG from natural language goal."""
    payload = {
        "goal": "Build distributed transactional ledger with MVCC",
        "dag_id": "dag-mvcc-01",
    }
    resp = client.post("/agents/dag-orchestrator/plan", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["dag_id"] == "dag-mvcc-01"
    assert len(data["nodes"]) == 6
    assert data["ready_node_ids"] == ["node-analyst"]
    assert "node-release" in data["topological_order"]


def test_get_dag_status_api(client: TestClient) -> None:
    """Test fetching DAG status and progress."""
    client.post(
        "/agents/dag-orchestrator/plan",
        json={"goal": "Implement Redis Sentinel Proxy", "dag_id": "dag-status-02"},
    )
    resp = client.get("/agents/dag-orchestrator/dag-status-02")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dag_id"] == "dag-status-02"
    assert data["is_completed"] is False
    assert "node-analyst" in data["nodes"]


def test_execute_dag_step_api(client: TestClient) -> None:
    """Test advancing ready nodes and unlocking dependent stages."""
    client.post(
        "/agents/dag-orchestrator/plan",
        json={"goal": "Refactor SIMD Parser", "dag_id": "dag-step-03"},
    )

    # Execute Analyst
    resp1 = client.post(
        "/agents/dag-orchestrator/dag-step-03/execute-step",
        json={"node_id": "node-analyst"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["nodes"]["node-analyst"]["status"] == "completed"
    assert data1["ready_node_ids"] == ["node-architect"]

    # Execute Architect -> both coders become ready in parallel
    resp2 = client.post(
        "/agents/dag-orchestrator/dag-step-03/execute-step",
        json={"node_id": "node-architect"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert sorted(data2["ready_node_ids"]) == ["node-coder-aux", "node-coder-core"]


def test_cold_resume_dag_api(client: TestClient) -> None:
    """Test restoring execution state from persistent checkpoint without re-running completed nodes."""
    client.post(
        "/agents/dag-orchestrator/plan",
        json={"goal": "Distributed Lock Manager", "dag_id": "dag-resume-04"},
    )
    # Execute Analyst and Architect
    client.post(
        "/agents/dag-orchestrator/dag-resume-04/execute-step",
        json={"node_id": "node-analyst"},
    )
    client.post(
        "/agents/dag-orchestrator/dag-resume-04/execute-step",
        json={"node_id": "node-architect"},
    )

    # Cold resume
    resp = client.post("/agents/dag-orchestrator/dag-resume-04/cold-resume")
    assert resp.status_code == 200
    data = resp.json()
    assert data["dag_id"] == "dag-resume-04"
    assert data["completed_count"] == 2
    assert sorted(data["ready_node_ids"]) == ["node-coder-aux", "node-coder-core"]


def test_reject_dag_node_api(client: TestClient) -> None:
    """Test bidirectional review loopback: reject upstream node and cascade reset downstream dependents."""
    client.post(
        "/agents/dag-orchestrator/plan",
        json={"goal": "Vector Search Engine", "dag_id": "dag-reject-05"},
    )

    # Advance analyst, architect, both coders, and tester
    for nid in ["node-analyst", "node-architect", "node-coder-core", "node-coder-aux", "node-tester"]:
        client.post(
            "/agents/dag-orchestrator/dag-reject-05/execute-step",
            json={"node_id": nid},
        )

    # Tester rejects architect contract
    reject_payload = {
        "target_node_id": "node-architect",
        "rejection_feedback": "Memory leak detected in persistent buffer allocation.",
    }
    resp = client.post("/agents/dag-orchestrator/dag-reject-05/reject", json=reject_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_node_id"] == "node-architect"
    assert data["nodes"]["node-architect"]["status"] == "rejected_loopback"
    assert "Memory leak" in data["nodes"]["node-architect"]["rejection_feedback"]

    # Downstream dependents (both coders and tester) are reset to pending
    assert data["nodes"]["node-coder-core"]["status"] == "pending"
    assert data["nodes"]["node-coder-aux"]["status"] == "pending"
    assert data["nodes"]["node-tester"]["status"] == "pending"
    assert data["next_ready_node_ids"] == ["node-architect"]


def test_dag_not_found_and_reset_api(client: TestClient) -> None:
    """Test 404 for nonexistent DAG and service reset."""
    resp = client.get("/agents/dag-orchestrator/nonexistent")
    assert resp.status_code == 404

    del_resp = client.delete("/agents/dag-orchestrator/reset")
    assert del_resp.status_code == 204
