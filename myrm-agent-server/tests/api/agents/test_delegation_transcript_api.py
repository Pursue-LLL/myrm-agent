# -*- coding: utf-8 -*-
"""Unit tests for Delegation Transcript, Persistent Ledger, and Smart Approvals API."""

from __future__ import annotations

from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.delegation_transcript_router import router as delegation_transcript_router
from app.services.agent.delegation_transcript_service import DelegationTranscriptService


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated DelegationTranscriptService."""
    DelegationTranscriptService.reset_instance()
    app = FastAPI()
    app.include_router(delegation_transcript_router)
    with TestClient(app) as test_client:
        yield test_client
    DelegationTranscriptService.reset_instance()


def test_task_lifecycle_api(client: TestClient) -> None:
    # 1. Create task
    res = client.post(
        "/delegation-transcript/tasks",
        json={
            "task_id": "task-api-001",
            "session_id": "sess-alpha",
            "subagent_id": "sub-worker-1",
            "role": "researcher",
            "prompt": "Evaluate competitor performance",
            "reasoning_effort": "medium",
        },
    )
    assert res.status_code == 201
    task = res.json()
    assert task["task_id"] == "task-api-001"
    assert task["status"] == "pending"

    # 2. Get task
    get_res = client.get("/delegation-transcript/tasks/task-api-001")
    assert get_res.status_code == 200
    assert get_res.json()["role"] == "researcher"

    # 3. Checkpoint
    ckp_res = client.post(
        "/delegation-transcript/tasks/task-api-001/checkpoint",
        json={
            "checkpoint_step": 2,
            "artifacts": [{"name": "report.json", "uri": "/tmp/report.json"}],
        },
    )
    assert ckp_res.status_code == 200
    assert ckp_res.json()["checkpoint_step"] == 2
    assert len(ckp_res.json()["artifacts"]) == 1

    # 4. Status update to completed
    stat_res = client.post(
        "/delegation-transcript/tasks/task-api-001/status",
        json={
            "status": "completed",
            "summary": "Completed analysis successfully",
        },
    )
    assert stat_res.status_code == 200
    assert stat_res.json()["status"] == "completed"
    assert stat_res.json()["summary"] == "Completed analysis successfully"
    assert stat_res.json()["finished_at"] is not None

    # 5. List tasks
    list_res = client.get("/delegation-transcript/tasks?session_id=sess-alpha")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1


def test_live_transcript_events_api(client: TestClient) -> None:
    # 1. Emit events
    ev1 = client.post(
        "/delegation-transcript/tasks/task-ev-1/events",
        json={
            "subagent_id": "sub-coder",
            "kind": "thought",
            "human_readable": "Inspecting AST syntax tree",
            "payload": {"step": 1},
        },
    )
    assert ev1.status_code == 201
    assert ev1.json()["seq"] == 1

    ev2 = client.post(
        "/delegation-transcript/tasks/task-ev-1/events",
        json={
            "subagent_id": "sub-coder",
            "kind": "tool_call",
            "human_readable": "Running lint check",
            "payload": {"tool": "oxlint"},
        },
    )
    assert ev2.status_code == 201
    assert ev2.json()["seq"] == 2

    # 2. Get events (all)
    all_evs = client.get("/delegation-transcript/tasks/task-ev-1/events")
    assert all_evs.status_code == 200
    assert len(all_evs.json()) == 2

    # 3. Get events after seq 1
    paged = client.get("/delegation-transcript/tasks/task-ev-1/events?after_seq=1")
    assert paged.status_code == 200
    assert len(paged.json()) == 1
    assert paged.json()[0]["seq"] == 2


def test_smart_approvals_lifecycle_api(client: TestClient) -> None:
    # 1. Evaluate high-risk command
    eval_res = client.post(
        "/delegation-transcript/approvals/evaluate",
        json={
            "task_id": "task-safe-1",
            "subagent_id": "sub-admin",
            "command": "rm -rf /tmp/build_cache",
        },
    )
    assert eval_res.status_code == 200
    appr = eval_res.json()
    approval_id = appr["approval_id"]
    assert appr["risk_score"] >= 0.9

    # 2. Resolve as approved
    res_appr = client.post(
        f"/delegation-transcript/approvals/{approval_id}/resolve",
        json={"decision": "approved"},
    )
    assert res_appr.status_code == 200
    assert res_appr.json()["decision"] == "approved"

    # 3. Consume approval once (success)
    c1 = client.post(f"/delegation-transcript/approvals/{approval_id}/consume")
    assert c1.status_code == 200
    assert c1.json()["consumed"] is True

    # 4. Consume approval twice (fails due to single-use bounding)
    c2 = client.post(f"/delegation-transcript/approvals/{approval_id}/consume")
    assert c2.status_code == 200
    assert c2.json()["consumed"] is False


def test_smart_approvals_interactive_deny_api(client: TestClient) -> None:
    eval_res = client.post(
        "/delegation-transcript/approvals/evaluate",
        json={
            "task_id": "task-safe-2",
            "subagent_id": "sub-admin",
            "command": "git push --force origin main",
        },
    )
    assert eval_res.status_code == 200
    approval_id = eval_res.json()["approval_id"]

    # Reject with /deny reason
    res_deny = client.post(
        f"/delegation-transcript/approvals/{approval_id}/resolve",
        json={
            "decision": "denied",
            "deny_reason": "Force push to main branch is strictly prohibited.",
        },
    )
    assert res_deny.status_code == 200
    data = res_deny.json()
    assert data["decision"] == "denied"
    assert data["deny_reason"] == "Force push to main branch is strictly prohibited."
    assert "remediation_prompt" in data
    assert "Force push to main" in data["remediation_prompt"]


def test_orphan_recovery_and_reasoning_allocation_api(client: TestClient) -> None:
    # 1. Register running task
    client.post(
        "/delegation-transcript/tasks",
        json={
            "task_id": "task-orphan-1",
            "session_id": "sess-recovery",
            "subagent_id": "sub-orphan",
            "role": "planner",
            "prompt": "Orphaned planning job",
            "reasoning_effort": "max",
        },
    )
    client.post(
        "/delegation-transcript/tasks/task-orphan-1/status",
        json={"status": "running"},
    )

    # 2. Trigger orphan recovery
    rec_res = client.post("/delegation-transcript/ledger/recover")
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["recovered_count"] >= 1
    assert any(t["task_id"] == "task-orphan-1" for t in rec_data["recovered_tasks"])

    # 3. Test reasoning effort allocation
    alloc_res = client.post(
        "/delegation-transcript/reasoning/allocate",
        json={"role": "architect"},
    )
    assert alloc_res.status_code == 200
    alloc_data = alloc_res.json()
    assert alloc_data["role"] == "architect"
    assert alloc_data["effort"] == "max"
    assert alloc_data["token_budget"] == 16384
