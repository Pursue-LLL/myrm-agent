"""Integration tests for Integration Egress Trust Lifecycle API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.integration_trust_router import (
    router as integration_trust_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting integration_trust_router."""
    test_app = FastAPI(title="Integration Trust Test App")
    test_app.include_router(integration_trust_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_get_and_list_disclosures_endpoint(client: TestClient) -> None:
    # 1. Retrieve Google Workspace disclosure card
    resp = client.get("/api/v1/security/integration-trust/disclosure/google_workspace")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_id"] == "google_workspace"
    assert "Gmail" in data["display_name"]
    assert len(data["data_types_read"]) > 0

    # 2. Retrieve non-existent disclosure card -> 404
    resp_404 = client.get("/api/v1/security/integration-trust/disclosure/unknown_provider_xyz")
    assert resp_404.status_code == 404

    # 3. List disclosures
    list_resp = client.get("/api/v1/security/integration-trust/disclosures")
    assert list_resp.status_code == 200
    all_data = list_resp.json()
    assert len(all_data) >= 3


def test_get_revoke_config_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/security/integration-trust/revoke-config/google_workspace")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider_id"] == "google_workspace"
    assert data["supports_remote_revoke"] is True
    assert "oauth2.googleapis.com" in data["revocation_endpoint"]
