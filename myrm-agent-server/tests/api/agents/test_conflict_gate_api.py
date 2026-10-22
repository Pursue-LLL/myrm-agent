"""Unit tests for Parallel Work Conflict Reconciliation Gate API endpoints.

[INPUT]
- app.api.agents.conflict_gate_router.router
- app.services.agent.conflict_gate_service.ConflictGateService
- myrm_agent_harness.agent.sub_agents.conflict_gate.ParallelWorkConflictDetector

[OUTPUT]
- Pytest test cases verifying collision evaluation, pending list, and resolution

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_conflict_gate_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.conflict_gate import (
    ParallelWorkConflictDetector,
)
from starlette.testclient import TestClient

from app.api.agents.conflict_gate_router import (
    get_conflict_gate_service,
)
from app.api.agents.conflict_gate_router import (
    router as conflict_gate_router,
)
from app.services.agent.conflict_gate_service import ConflictGateService


@pytest.fixture
def mock_conflict_gate_service() -> ConflictGateService:
    detector = ParallelWorkConflictDetector()
    return ConflictGateService(detector=detector)


@pytest.fixture
def conflict_gate_client(
    mock_conflict_gate_service: ConflictGateService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(conflict_gate_router)
    app.dependency_overrides[get_conflict_gate_service] = lambda: mock_conflict_gate_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_evaluate_clean_writes_api(conflict_gate_client: TestClient) -> None:
    session_id = "sess-clean-001"
    req_body = {
        "fingerprints": [
            {
                "worker_id": "worker-1",
                "resource_id": "src/utils.py",
                "mutation_type": "file",
                "content_hash": "hash-clean-1",
                "summary": "Add string helper",
            }
        ]
    }
    resp = conflict_gate_client.post(f"/chats/{session_id}/conflicts/evaluate", json=req_body)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == session_id
    assert data["is_blocked"] is False
    assert data["total_conflicts"] == 0
    assert len(data["clean_writes"]) == 1


def test_evaluate_hash_collision_blocked_api(conflict_gate_client: TestClient) -> None:
    session_id = "sess-conflict-002"
    req_body = {
        "fingerprints": [
            {
                "worker_id": "worker-coder",
                "resource_id": "schema.prisma",
                "mutation_type": "file",
                "content_hash": "hash-prisma-v1",
                "summary": "Add User model",
            },
            {
                "worker_id": "worker-architect",
                "resource_id": "schema.prisma",
                "mutation_type": "file",
                "content_hash": "hash-prisma-v2",
                "summary": "Refactor to Account model",
            },
        ]
    }
    resp = conflict_gate_client.post(f"/chats/{session_id}/conflicts/evaluate", json=req_body)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_blocked"] is True
    assert data["total_conflicts"] == 1
    assert len(data["conflicts"]) == 1

    conflict = data["conflicts"][0]
    assert conflict["resource_id"] == "schema.prisma"
    assert conflict["status"] == "conflict_pending"


def test_get_pending_conflicts_and_resolve_api(conflict_gate_client: TestClient) -> None:
    session_id = "sess-resolve-003"
    # 1. Trigger a conflict first
    req_body = {
        "fingerprints": [
            {
                "worker_id": "w1",
                "resource_id": "config.yaml",
                "mutation_type": "config",
                "content_hash": "hash-yaml-1",
            },
            {
                "worker_id": "w2",
                "resource_id": "config.yaml",
                "mutation_type": "config",
                "content_hash": "hash-yaml-2",
            },
        ]
    }
    eval_resp = conflict_gate_client.post(f"/chats/{session_id}/conflicts/evaluate", json=req_body)
    conflict_id = eval_resp.json()["data"]["conflicts"][0]["conflict_id"]

    # 2. Get pending conflicts list
    pending_resp = conflict_gate_client.get(f"/chats/{session_id}/conflicts")
    assert pending_resp.status_code == 200
    pending_list = pending_resp.json()["data"]
    assert len(pending_list) == 1
    assert pending_list[0]["conflict_id"] == conflict_id

    # 3. Resolve conflict with keep_worker_a
    resolve_resp = conflict_gate_client.post(
        f"/chats/{session_id}/conflicts/{conflict_id}/resolve",
        json={"strategy": "keep_worker_a", "resolved_content": None},
    )
    assert resolve_resp.status_code == 200
    res_data = resolve_resp.json()["data"]
    assert res_data["success"] is True
    assert res_data["conflict"]["status"] == "resolved"
    assert res_data["conflict"]["resolution_strategy"] == "keep_worker_a"

    # 4. Verify pending list is now empty
    empty_pending_resp = conflict_gate_client.get(f"/chats/{session_id}/conflicts")
    assert len(empty_pending_resp.json()["data"]) == 0
