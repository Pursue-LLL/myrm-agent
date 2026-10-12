"""API endpoint tests for Connector Catalog Trust Grading and Server Review Provenance."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.connector_trust_router import (
    router as connector_trust_router,
)
from app.core.integrations.catalog.trust_registry import CatalogTrustRegistry
from app.services.security.connector_trust_service import (
    ConnectorTrustService,
    get_connector_trust_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ConnectorTrustService(registry=CatalogTrustRegistry())
    app = FastAPI()
    app.include_router(connector_trust_router)
    app.dependency_overrides[get_connector_trust_service] = lambda: test_service
    return TestClient(app)


def test_list_and_get_trust_profiles_endpoints(client: TestClient) -> None:
    # 1. List profiles
    resp_list = client.get("/security/connector-trust/profiles")
    assert resp_list.status_code == 200
    profiles = resp_list.json()
    assert isinstance(profiles, list)
    assert len(profiles) >= 3

    # 2. Get official verified profile
    resp_get = client.get("/security/connector-trust/profiles/github")
    assert resp_get.status_code == 200
    gh = resp_get.json()
    assert gh["connector_id"] == "github"
    assert gh["trust_tier"] == "OFFICIAL_VERIFIED"
    assert "list_issues" in gh["least_privilege"]["recommended_tools"]

    # 3. Get unreviewed fallback profile
    resp_unrev = client.get("/security/connector-trust/profiles/custom-unregistered")
    assert resp_unrev.status_code == 200
    unrev = resp_unrev.json()
    assert unrev["connector_id"] == "custom-unregistered"
    assert unrev["trust_tier"] == "UNREVIEWED"


def test_preflight_verified_vs_unreviewed_endpoints(client: TestClient) -> None:
    # 1. Preflight verified without drift
    resp_ver = client.post(
        "/security/connector-trust/preflight",
        json={"connector_id": "github", "target_version": "v0.6.2"},
    )
    assert resp_ver.status_code == 200
    data_ver = resp_ver.json()
    assert data_ver["is_approved_for_install"] is True
    assert data_ver["requires_explicit_unreviewed_confirmation"] is False
    assert data_ver["has_provenance_drift"] is False

    # 2. Preflight unreviewed requires confirmation
    resp_unrev = client.post(
        "/security/connector-trust/preflight",
        json={"connector_id": "arbitrary-random-mcp"},
    )
    assert resp_unrev.status_code == 200
    data_unrev = resp_unrev.json()
    assert data_unrev["is_approved_for_install"] is False
    assert data_unrev["requires_explicit_unreviewed_confirmation"] is True
    assert "NOT audited by Myrm Security" in data_unrev["unreviewed_risk_disclosure"]


def test_continuous_review_endpoint(client: TestClient) -> None:
    resp = client.post("/security/connector-trust/continuous-review")
    assert resp.status_code == 200
    report = resp.json()
    assert "total_audited" in report
    assert report["total_audited"] >= 3
    assert "audit_timestamp" in report


def test_unreviewed_disclosure_endpoint(client: TestClient) -> None:
    # 1. Unreviewed disclosure
    resp_unrev = client.get("/security/connector-trust/unreviewed-disclosure/unknown-service")
    assert resp_unrev.status_code == 200
    data_unrev = resp_unrev.json()
    assert data_unrev["risk_acknowledgement_required"] is True
    assert "SECURITY DISCLOSURE" in data_unrev["disclosure_text"]

    # 2. Reviewed disclosure
    resp_rev = client.get("/security/connector-trust/unreviewed-disclosure/github")
    assert resp_rev.status_code == 200
    data_rev = resp_rev.json()
    assert data_rev["risk_acknowledgement_required"] is False
