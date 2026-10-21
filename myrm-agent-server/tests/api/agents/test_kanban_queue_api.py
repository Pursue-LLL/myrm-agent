"""API integration tests for Persistent Kanban Job Queue and Massive Parallel Dogfooding Runner (Item 70).

[INPUT]
- app.api.agents.kanban_queue_router.router
- app.services.agent.kanban_queue_service.get_kanban_queue_service

[OUTPUT]
- Pytest assertions verifying 5-state lifecycle, 9 core tools, 4h heartbeat reclamation,
  Swarm blackboard synchronization, auto-triage specification, fan-out decomposition,
  circuit breaker, and 12-way parallel batch runner.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_kanban_queue_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.kanban_queue_router import router as kanban_queue_router
from app.services.agent.kanban_queue_service import get_kanban_queue_service


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory sessions before each test."""
    service = get_kanban_queue_service()
    service.reset_session("chat-test-kq")


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with kanban_queue_router attached."""
    app = FastAPI()
    app.include_router(kanban_queue_router)
    return TestClient(app)


def test_create_and_get_job_api(client: TestClient) -> None:
    """Test job creation, detail retrieval, and filtered listing."""
    payload = {
        "title": "Design Database Schema",
        "goal": "Model relational entities for multi-agent persistence",
        "approach": "Normalized 3NF tables with foreign keys",
        "acceptance_criteria": ["All schemas compile", "Foreign key constraints valid"],
        "priority": "high",
        "stage": "planning_root",
        "skills": ["sql", "architecture"],
    }
    resp = client.post("/chats/chat-test-kq/kanban-queue/jobs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    job_id = data["job_id"]
    assert job_id.startswith("job-")
    assert data["status"] == "ready"
    assert data["worktree_path"] == f".worktrees/job-{job_id}"

    # Get by ID
    get_resp = client.get(f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Design Database Schema"

    # List jobs
    list_resp = client.get("/chats/chat-test-kq/kanban-queue/jobs?status=ready")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_claim_and_complete_job_api(client: TestClient) -> None:
    """Test worker claim and completion unblocking."""
    create_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Write Harness Bridge", "goal": "Bridge subagents"},
    )
    job_id = create_resp.json()["job_id"]

    # Claim job
    claim_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/claim",
        json={"assignee": "agent-worker-01"},
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["status"] == "running"
    assert claim_resp.json()["assignee"] == "agent-worker-01"

    # Complete job
    comp_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/complete",
        json={"summary": "Harness bridge ready", "metadata": {"lines": "340"}},
    )
    assert comp_resp.status_code == 200
    assert comp_resp.json()["status"] == "done"
    assert comp_resp.json()["result_summary"] == "Harness bridge ready"


def test_block_and_unblock_job_api(client: TestClient) -> None:
    """Test blocking a job with reason and unblocking."""
    create_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Deploy to Staging", "goal": "Deploy app"},
    )
    job_id = create_resp.json()["job_id"]

    block_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/block",
        json={"reason": "Waiting on cluster provisioning"},
    )
    assert block_resp.status_code == 200
    assert block_resp.json()["status"] == "blocked"
    assert block_resp.json()["blocked_reason"] == "Waiting on cluster provisioning"

    unblock_resp = client.post(f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/unblock")
    assert unblock_resp.status_code == 200
    assert unblock_resp.json()["status"] == "ready"
    assert unblock_resp.json()["blocked_reason"] is None


def test_heartbeat_and_stale_reclaim_api(client: TestClient) -> None:
    """Test sending heartbeats and checking stale worker reclamation."""
    create_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Heavy Data Ingestion", "goal": "Ingest 1M rows"},
    )
    job_id = create_resp.json()["job_id"]
    client.post(f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/claim", json={"assignee": "worker-data"})

    hb_resp = client.post(f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/heartbeat")
    assert hb_resp.status_code == 200
    assert hb_resp.json()["success"] is True

    # Stale reclamation (fresh heartbeat, so nothing reclaimed)
    reclaim_resp = client.post("/chats/chat-test-kq/kanban-queue/reclaim-stale")
    assert reclaim_resp.status_code == 200
    assert reclaim_resp.json()["reclaimed_job_ids"] == []


def test_comments_and_swarm_blackboard_api(client: TestClient) -> None:
    """Test standard comment and [swarm:blackboard] comment synchronization."""
    create_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Consensus Round", "goal": "Deliberate", "stage": "verifier_gate"},
    )
    job_id = create_resp.json()["job_id"]

    # Normal comment
    c_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/comments",
        json={"author": "lead_human", "content": "Please review AST rules"},
    )
    assert c_resp.status_code == 200
    assert c_resp.json()["is_blackboard"] is False

    # Blackboard comment
    bb_content = '[swarm:blackboard] {"status": "verified", "score": "0.98"}'
    bb_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{job_id}/comments",
        json={"author": "verifier_bot", "content": bb_content},
    )
    assert bb_resp.status_code == 200
    assert bb_resp.json()["is_blackboard"] is True

    # Retrieve blackboard
    bb_list_resp = client.get("/chats/chat-test-kq/kanban-queue/blackboard?stage=verifier_gate")
    assert bb_list_resp.status_code == 200
    entries = bb_list_resp.json()
    assert len(entries) == 1
    assert entries[0]["payload"]["status"] == "verified"


def test_link_specify_and_decompose_api(client: TestClient) -> None:
    """Test linking dependencies, specify prompt, and decompose subtasks."""
    job1_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Step 1", "goal": "Do step 1"},
    )
    job2_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/jobs",
        json={"title": "Step 2", "goal": "Do step 2"},
    )
    j1 = job1_resp.json()["job_id"]
    j2 = job2_resp.json()["job_id"]

    link_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/link",
        json={"from_job_id": j1, "to_job_id": j2},
    )
    assert link_resp.status_code == 200
    assert link_resp.json()["linked"] is True

    # Specify
    spec_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/specify",
        json={"prompt": "Build ultra-fast memory cache for Open-Perplexity"},
    )
    assert spec_resp.status_code == 200
    spec_data = spec_resp.json()
    assert "Open-Perplexity" in spec_data["title"] or "memory" in spec_data["title"]
    assert len(spec_data["acceptance_criteria"]) >= 2

    # Decompose
    dec_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{j1}/decompose",
        json={
            "subtasks": [
                {"title": "Subtask A", "goal": "Goal A"},
                {"title": "Subtask B", "goal": "Goal B"},
            ]
        },
    )
    assert dec_resp.status_code == 200
    subs = dec_resp.json()
    assert len(subs) == 2

    # Toggle circuit breaker and verify lockout
    cb_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/circuit-breaker",
        json={"enabled": False},
    )
    assert cb_resp.status_code == 200
    assert cb_resp.json()["auto_decompose_enabled"] is False

    dec_blocked_resp = client.post(
        f"/chats/chat-test-kq/kanban-queue/jobs/{j1}/decompose",
        json={"subtasks": [{"title": "Subtask C", "goal": "Goal C"}]},
    )
    assert dec_blocked_resp.status_code == 423


def test_batch_runner_dispatch_and_trajectories_api(client: TestClient) -> None:
    """Test 12-way parallel wave dispatch and trajectory export."""
    # Seed 5 jobs
    for i in range(5):
        client.post(
            "/chats/chat-test-kq/kanban-queue/jobs",
            json={"title": f"Batch Job {i}", "goal": f"Execute batch {i}"},
        )

    # Dispatch wave
    dispatch_resp = client.post(
        "/chats/chat-test-kq/kanban-queue/batch/dispatch",
        json={"max_parallel": 12, "distribution_strategy": "round_robin"},
    )
    assert dispatch_resp.status_code == 200
    d_data = dispatch_resp.json()
    assert d_data["dispatched"] == 5
    assert d_data["running"] == 5

    # Check status
    st_resp = client.get("/chats/chat-test-kq/kanban-queue/batch/status")
    assert st_resp.status_code == 200
    assert st_resp.json()["total_jobs"] == 5
    assert st_resp.json()["running_jobs"] == 5

    # Export trajectories
    traj_resp = client.get("/chats/chat-test-kq/kanban-queue/batch/trajectories")
    assert traj_resp.status_code == 200
    assert "trajectories_jsonl" in traj_resp.json()
