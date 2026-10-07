"""
[POS] tests/api/agents/test_agent_handoff_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.agents.agent_handoff_router
[OUTPUT] test_finalize_and_get_handoff_api, test_list_pending_handoffs_api, test_claim_handoff_cas_and_mismatch_api, test_complete_and_cancel_lifecycle_api
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.handoff import AgentHandoffEngine
from starlette.testclient import TestClient

from app.api.agents.agent_handoff_router import router as agent_handoff_router
from app.services.agent.agent_handoff_service import (
    AgentHandoffService,
    get_agent_handoff_service,
)


@pytest.fixture
def handoff_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture mounting agent handoff router."""
    storage_dir = tmp_path / "server_handoffs"
    engine = AgentHandoffEngine(storage_dir=storage_dir)
    service = AgentHandoffService(engine=engine)

    test_app = FastAPI()
    test_app.include_router(agent_handoff_router, prefix="/api/agents")
    test_app.dependency_overrides[get_agent_handoff_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_finalize_and_get_handoff_api(handoff_client: TestClient) -> None:
    """Verify POST /finalize creates a durable handoff memorandum and GET retrieves it."""
    req_payload = {
        "session_id": "sess-init-01",
        "source_profile_id": "architect",
        "target_profile_id": "engineer",
        "active_goal": "Migrate database schema with zero downtime",
        "failed_approaches": [
            {
                "approach_name": "ALTER TABLE direct lock",
                "rejected_reason": "Blocks write queries in production",
                "evidence_snippet": "QueryTimeoutError: lock wait timeout exceeded",
                "attempted_by_profile_id": "architect",
            }
        ],
        "implicit_constraints": [
            {
                "scope": "database",
                "constraint_rule": "Online DDL with gh-ost or pt-online-schema-change required",
                "rationale": "High throughput OLTP service",
            }
        ],
        "errors_and_fixes": ["Deadlock detected -> batch updates into 500 row chunks"],
        "pending_asks": ["Confirm maintenance window timing with SRE"],
        "next_actions": ["Write shadow table schema", "Run validation probe"],
    }

    # 1. Finalize
    resp = handoff_client.post("/api/agents/handoff/finalize", json=req_payload)
    assert resp.status_code == 201
    fin_data = resp.json()
    assert fin_data["session_id"] == "sess-init-01"
    assert fin_data["status"] == "pending"
    handoff_id = fin_data["handoff_id"]
    assert handoff_id.startswith("handoff-")

    # 2. Get by ID
    get_resp = handoff_client.get(f"/api/agents/handoff/{handoff_id}")
    assert get_resp.status_code == 200
    spec_data = get_resp.json()
    assert spec_data["handoff_id"] == handoff_id
    assert spec_data["source_profile_id"] == "architect"
    assert spec_data["target_profile_id"] == "engineer"
    assert len(spec_data["failed_approaches"]) == 1
    assert spec_data["failed_approaches"][0]["approach_name"] == "ALTER TABLE direct lock"
    assert len(spec_data["implicit_constraints"]) == 1
    assert spec_data["status"] == "pending"


def test_list_pending_handoffs_api(handoff_client: TestClient) -> None:
    """Verify GET /pending lists open handoffs with profile filtering."""
    # Create one targeted to 'specialist' and one open (None)
    handoff_client.post(
        "/api/agents/handoff/finalize",
        json={
            "session_id": "sess-1",
            "source_profile_id": "lead",
            "target_profile_id": "specialist",
            "active_goal": "Specialized tuning",
        },
    )
    handoff_client.post(
        "/api/agents/handoff/finalize",
        json={
            "session_id": "sess-2",
            "source_profile_id": "lead",
            "target_profile_id": None,
            "active_goal": "General task",
        },
    )

    # List all
    all_resp = handoff_client.get("/api/agents/handoff/pending")
    assert all_resp.status_code == 200
    assert all_resp.json()["total_count"] == 2

    # Filter by specialist
    spec_resp = handoff_client.get("/api/agents/handoff/pending?target_profile_id=specialist")
    assert spec_resp.status_code == 200
    # Returns both target_profile_id='specialist' and target_profile_id=None
    assert spec_resp.json()["total_count"] == 2

    # Filter by other -> only gets unassigned (None)
    other_resp = handoff_client.get("/api/agents/handoff/pending?target_profile_id=other")
    assert other_resp.status_code == 200
    assert other_resp.json()["total_count"] == 1


def test_claim_handoff_cas_and_mismatch_api(handoff_client: TestClient) -> None:
    """Verify CAS exactly-once claim semantics and profile mismatch guards."""
    fin_resp = handoff_client.post(
        "/api/agents/handoff/finalize",
        json={
            "session_id": "sess-parent",
            "source_profile_id": "parent",
            "target_profile_id": "designated-child",
            "active_goal": "Handover to designated child",
        },
    )
    handoff_id = fin_resp.json()["handoff_id"]

    # 1. Mismatch claim -> 403 Forbidden
    mismatch_resp = handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/claim",
        json={
            "claimer_profile_id": "intruder-profile",
            "claimer_session_id": "sess-child-intruder",
        },
    )
    assert mismatch_resp.status_code == 403

    # 2. Designated claim -> 200 OK
    claim_resp = handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/claim",
        json={
            "claimer_profile_id": "designated-child",
            "claimer_session_id": "sess-child-legit",
        },
    )
    assert claim_resp.status_code == 200
    claim_data = claim_resp.json()
    assert claim_data["claimed_by_profile_id"] == "designated-child"
    assert claim_data["handoff_spec"]["status"] == "claimed"

    # 3. Duplicate claim -> 409 Conflict
    dup_resp = handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/claim",
        json={
            "claimer_profile_id": "designated-child",
            "claimer_session_id": "sess-child-dup",
        },
    )
    assert dup_resp.status_code == 409


def test_complete_and_cancel_lifecycle_api(handoff_client: TestClient) -> None:
    """Verify complete and cancel transitions through REST endpoints."""
    fin_resp = handoff_client.post(
        "/api/agents/handoff/finalize",
        json={
            "session_id": "sess-run",
            "source_profile_id": "p1",
            "active_goal": "Run through complete lifecycle",
        },
    )
    handoff_id = fin_resp.json()["handoff_id"]

    # Claim
    handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/claim",
        json={
            "claimer_profile_id": "p2",
            "claimer_session_id": "sess-p2",
        },
    )

    # Complete
    complete_resp = handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/complete",
        json={"completing_session_id": "sess-p2"},
    )
    assert complete_resp.status_code == 200
    assert complete_resp.json()["status"] == "completed"

    # Cannot cancel completed handoff -> 409 Conflict
    cancel_resp = handoff_client.post(
        f"/api/agents/handoff/{handoff_id}/cancel",
        json={"cancelling_session_id": "sess-p2", "reason": "No longer needed"},
    )
    assert cancel_resp.status_code == 409
