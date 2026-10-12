"""Integration tests for Local Action Ledger and Privacy Inspector API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.audit.local_action_router import router as local_action_router
from app.services.audit.egress_footprint_ledger import get_egress_footprint_ledger


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting local action router."""
    test_app = FastAPI(title="Local Action Audit Test App")
    test_app.include_router(local_action_router, prefix="/api/v1")
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.mark.asyncio
async def test_local_action_endpoints_full_cycle(client: TestClient) -> None:
    """Test full cycle: record access, list, verify chain, query egress, and export dossier."""
    # 1. POST record access
    record_payload = {
        "agent_id": "agent-triage",
        "target_entity_type": "email",
        "target_entity_id": "em-msg-5566",
        "entity_hash": "sha256-dummy-email-hash",
        "action": "classify",
        "intent_summary": "Triage customer incoming email for billing department",
        "operator_or_model": "gpt-4o",
        "session_id": "sess-xyz",
        "task_id": "task-abc",
    }
    resp = client.post("/api/v1/audit/local-actions", json=record_payload)
    assert resp.status_code == 200
    entry_data = resp.json()
    assert entry_data["entry_id"] != ""
    assert entry_data["agent_id"] == "agent-triage"
    assert entry_data["target_entity_type"] == "email"
    assert entry_data["signature"] != ""
    assert entry_data["entry_hash"] != ""

    # 2. GET list actions
    list_resp = client.get("/api/v1/audit/local-actions?agent_id=agent-triage")
    assert list_resp.status_code == 200
    entries = list_resp.json()
    assert len(entries) >= 1
    assert entries[0]["agent_id"] == "agent-triage"

    # 3. GET verify chain
    verify_resp = client.get("/api/v1/audit/local-actions/verify")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["healthy"] is True
    assert verify_data["error"] is None
    assert verify_data["total_entries_verified"] >= 1

    # 4. Inject an egress footprint directly into service
    egress_ledger = get_egress_footprint_ledger()
    await egress_ledger.record_egress(
        agent_id="agent-triage",
        target_host="api.external-crm.com",
        target_url="https://api.external-crm.com/v1/sync",
        content_summary="Sync ticket metadata",
        method="POST",
        sensitivity_level="MEDIUM",
    )

    # GET egress footprints
    egress_resp = client.get("/api/v1/audit/local-actions/egress-footprints?agent_id=agent-triage")
    assert egress_resp.status_code == 200
    footprints = egress_resp.json()
    assert len(footprints) >= 1
    assert footprints[0]["target_host"] == "api.external-crm.com"

    # 5. GET inspector summary
    summary_resp = client.get("/api/v1/audit/local-actions/inspector-summary?agent_id=agent-triage")
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert summary_data["agent_id"] == "agent-triage"
    assert summary_data["ledger_chain_healthy"] is True
    assert summary_data["total_sensitive_entities_read"] >= 1

    # 6. GET export dossier
    export_resp = client.get("/api/v1/audit/local-actions/export?agent_id=agent-triage")
    assert export_resp.status_code == 200
    dossier = export_resp.json()
    assert dossier["chain_verification"]["healthy"] is True
    assert len(dossier["local_action_entries"]) >= 1
    assert len(dossier["egress_footprints"]) >= 1
