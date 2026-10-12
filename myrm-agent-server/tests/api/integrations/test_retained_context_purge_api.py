"""Unit tests for integration retained context governance, purge, and provenance revocation API.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.integrations.retained_context_router, app.services.memory.integration_purge_service

[OUTPUT]
- test_get_retained_context_summary_api
- test_disconnect_with_retain_context_mode_api
- test_disconnect_with_purge_and_revoke_mode_api
- test_list_revocation_audit_records_api
- test_reinstate_provenance_api

[POS]
Integration/API tests for connector retained context inspection, selective purge,
Dots parity mode, and provenance revocation ledger endpoints (Topic 01 Item 179).
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.integrations.retained_context_router import router as retained_context_router
from app.services.memory.integration_purge_service import (
    IntegrationContextPurgeService,
    get_integration_purge_service,
)


@pytest.fixture
def retained_context_test_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient with freshly initialized purge service instance."""
    service = IntegrationContextPurgeService()
    # Seed mock records for testing
    mgr = service.get_underlying_manager()
    t1 = datetime(2026, 10, 2, 9, 30, tzinfo=UTC)
    t2 = datetime(2026, 10, 6, 15, 45, tzinfo=UTC)
    mgr.register_mock_record("google_workspace", "Spreadsheet summary: FY26 Q1 Revenue", t1)
    mgr.register_mock_record("google_workspace", "Doc snippet: API security standards v2", t2)

    test_app = FastAPI()
    test_app.include_router(retained_context_router, prefix="/api/integrations/retained-context")
    test_app.dependency_overrides[get_integration_purge_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_get_retained_context_summary_api(retained_context_test_client: TestClient) -> None:
    """Test retrieving retained context summary snapshot for a connector."""
    response = retained_context_test_client.get(
        "/api/integrations/retained-context/summary/google_workspace?provider_type=oauth_provider"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["integration_id"] == "google_workspace"
    assert data["provider_type"] == "oauth_provider"
    assert data["retained_memory_count"] == 2
    assert data["total_retained_items"] == 2
    assert len(data["sample_snippets"]) == 2
    assert "Spreadsheet summary" in data["sample_snippets"][0]
    assert data["is_provenance_revoked"] is False


def test_disconnect_with_retain_context_mode_api(retained_context_test_client: TestClient) -> None:
    """Test disconnecting with retain_context mode (Dots parity): preserves context data."""
    payload = {
        "purge_mode": "retain_context",
        "confirm_purge": False,
        "reason": "Disconnecting Google Workspace account but keeping past memory",
    }
    response = retained_context_test_client.post(
        "/api/integrations/retained-context/disconnect-with-purge/google_workspace",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["integration_id"] == "google_workspace"
    assert data["disconnected"] is True
    assert data["purged_items"] == 0
    assert data["mode"] == "retain_context"
    assert data["revocation_id"] is None

    # Context should remain intact
    summary_resp = retained_context_test_client.get(
        "/api/integrations/retained-context/summary/google_workspace"
    )
    assert summary_resp.status_code == 200
    assert summary_resp.json()["total_retained_items"] == 2
    assert summary_resp.json()["is_provenance_revoked"] is False


def test_disconnect_with_purge_and_revoke_mode_api(
    retained_context_test_client: TestClient,
) -> None:
    """Test disconnecting with purge_and_revoke: cleans up data and records revocation."""
    payload = {
        "purge_mode": "purge_and_revoke",
        "confirm_purge": True,
        "reason": "Compliance mandate: complete erasure and provenance invalidation",
    }
    response = retained_context_test_client.post(
        "/api/integrations/retained-context/disconnect-with-purge/google_workspace?actor=admin_user",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["integration_id"] == "google_workspace"
    assert data["disconnected"] is True
    assert data["purged_items"] == 2
    assert data["mode"] == "purge_and_revoke"
    assert data["revocation_id"] is not None

    # After purge, retained count should be 0 and provenance should be marked revoked
    summary_resp = retained_context_test_client.get(
        "/api/integrations/retained-context/summary/google_workspace"
    )
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total_retained_items"] == 0
    assert summary["is_provenance_revoked"] is True


def test_list_revocation_audit_records_api(retained_context_test_client: TestClient) -> None:
    """Test retrieving historical provenance revocation audit records."""
    # First execute a purge and revoke
    payload = {
        "purge_mode": "purge_and_revoke",
        "confirm_purge": True,
        "reason": "Audit trail test revocation",
    }
    retained_context_test_client.post(
        "/api/integrations/retained-context/disconnect-with-purge/google_workspace?actor=auditor",
        json=payload,
    )

    # Query revocation ledger
    response = retained_context_test_client.get("/api/integrations/retained-context/revocations")
    assert response.status_code == 200
    records = response.json()
    assert len(records) >= 1
    target = next((r for r in records if r["integration_id"] == "google_workspace"), None)
    assert target is not None
    assert target["actor"] == "auditor"
    assert "Audit trail test" in target["reason"]
    assert target["purged_items_count"] == 2


def test_reinstate_provenance_api(retained_context_test_client: TestClient) -> None:
    """Test reinstating a revoked provenance source anchor."""
    # Revoke first
    retained_context_test_client.post(
        "/api/integrations/retained-context/disconnect-with-purge/google_workspace",
        json={"purge_mode": "purge_and_revoke", "confirm_purge": True},
    )

    # Check revoked
    summary_before = retained_context_test_client.get(
        "/api/integrations/retained-context/summary/google_workspace"
    ).json()
    assert summary_before["is_provenance_revoked"] is True

    # Reinstate
    response = retained_context_test_client.post(
        "/api/integrations/retained-context/reinstate/google_workspace"
    )
    assert response.status_code == 200
    assert response.json()["reinstated"] is True

    # Check revoked status reset
    summary_after = retained_context_test_client.get(
        "/api/integrations/retained-context/summary/google_workspace"
    ).json()
    assert summary_after["is_provenance_revoked"] is False
