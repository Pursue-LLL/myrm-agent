"""
[POS] tests/api/security/test_enterprise_hipaa_compliance_endpoints.py
Integration tests for Enterprise BAA / HIPAA Compliance Conduit REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.enterprise_hipaa_compliance_router import (
    router as enterprise_hipaa_compliance_router,
)
from app.services.security.enterprise_hipaa_compliance_service import (
    EnterpriseHipaaComplianceService,
    get_enterprise_hipaa_compliance_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = EnterpriseHipaaComplianceService()
    app = FastAPI()
    app.include_router(enterprise_hipaa_compliance_router)
    app.dependency_overrides[get_enterprise_hipaa_compliance_service] = lambda: service
    return TestClient(app)


def test_endpoint_provider_lifecycle(client: TestClient) -> None:
    # 1. List existing providers
    resp_list = client.get("/enterprise-hipaa-compliance/providers")
    assert resp_list.status_code == 200
    providers = resp_list.json()
    assert len(providers) >= 2

    # 2. Register custom provider
    resp_reg = client.post(
        "/enterprise-hipaa-compliance/providers",
        json={
            "provider_id": "google-vertex-hipaa-central",
            "provider_name": "Google Vertex AI MedLM",
            "base_url": "https://us-central1-aiplatform.googleapis.com",
            "tier": "verified_baa_signed",
            "baa_agreement_id": "BAA-GOOG-2026-99",
            "is_zero_training_mandated": True,
            "permitted_models": ["medlm-large", "gemini-1.5-pro"],
        },
    )
    assert resp_reg.status_code == 200
    reg_data = resp_reg.json()
    assert reg_data["provider_id"] == "google-vertex-hipaa-central"

    # 3. Get provider by ID
    resp_get = client.get("/enterprise-hipaa-compliance/providers/google-vertex-hipaa-central")
    assert resp_get.status_code == 200
    assert resp_get.json()["baa_agreement_id"] == "BAA-GOOG-2026-99"

    # 4. Get 404 for unknown
    resp_404 = client.get("/enterprise-hipaa-compliance/providers/unknown-xyz")
    assert resp_404.status_code == 404


def test_endpoint_audit_recording_and_integrity(client: TestClient) -> None:
    # 1. Record event #1
    resp1 = client.post(
        "/enterprise-hipaa-compliance/audit/events",
        json={
            "event_type": "ehr_access",
            "agent_id": "agent-dr-smith",
            "session_id": "session-hosp-77",
            "action_summary": "Access diagnostic lab charts",
            "phi_detected": True,
        },
    )
    assert resp1.status_code == 200
    entry1 = resp1.json()
    assert entry1["sequence_index"] == 0
    assert entry1["phi_detected"] is True
    assert len(entry1["current_hash"]) == 64

    # 2. Record event #2
    resp2 = client.post(
        "/enterprise-hipaa-compliance/audit/events",
        json={
            "event_type": "tool_execution",
            "agent_id": "agent-scribe",
            "session_id": "session-hosp-77",
            "action_summary": "Lookup ICD-10 diagnostic codes",
            "phi_detected": False,
        },
    )
    assert resp2.status_code == 200
    entry2 = resp2.json()
    assert entry2["sequence_index"] == 1
    assert entry2["prev_hash"] == entry1["current_hash"]

    # 3. Verify unbroken chain
    resp_verify = client.get("/enterprise-hipaa-compliance/audit/verify")
    assert resp_verify.status_code == 200
    assert resp_verify.json()["is_valid"] is True


def test_endpoint_export_compliance_package(client: TestClient) -> None:
    # Record one event first
    client.post(
        "/enterprise-hipaa-compliance/audit/events",
        json={
            "event_type": "export_request",
            "agent_id": "compliance-officer",
            "session_id": "session-audit-33",
            "action_summary": "Annual healthcare compliance export",
            "phi_detected": False,
        },
    )

    # Export package
    resp = client.post(
        "/enterprise-hipaa-compliance/audit/export",
        json={"compliance_standard": "hipaa"},
    )
    assert resp.status_code == 200
    pkg = resp.json()
    assert pkg["export_id"].startswith("exp-")
    assert pkg["compliance_standard"] == "hipaa"
    assert pkg["chain_valid"] is True
    assert pkg["total_events"] >= 1
    assert len(pkg["summary_digest"]) == 64


def test_endpoint_screen_phi(client: TestClient) -> None:
    resp = client.post(
        "/enterprise-hipaa-compliance/phi/screen",
        json={"content": "Patient has MRN MRN-99881122 and SSN 456-78-9012."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_clean"] is False
    assert len(data["detected_phi_categories"]) >= 2
    assert "[REDACTED_SSN]" in data["sanitized_content"]
    assert "456-78-9012" not in data["sanitized_content"]


def test_endpoint_validate_egress_and_metrics(client: TestClient) -> None:
    # 1. Valid BAA signed endpoint
    resp_valid = client.post(
        "/enterprise-hipaa-compliance/egress/validate",
        json={
            "provider_id": "azure-openai-enterprise-eastus",
            "content": "Patient has fever and cough.",
        },
    )
    assert resp_valid.status_code == 200
    data_valid = resp_valid.json()
    assert data_valid["allowed"] is True
    assert data_valid["headers"]["X-Opt-Out-Training"] == "true"

    # 2. Unregistered endpoint
    resp_invalid = client.post(
        "/enterprise-hipaa-compliance/egress/validate",
        json={
            "provider_id": "unregistered-public-llm",
            "content": "Clinical notes",
        },
    )
    assert resp_invalid.status_code == 200
    assert resp_invalid.json()["allowed"] is False

    # 3. Telemetry metrics endpoint
    resp_metrics = client.get("/enterprise-hipaa-compliance/metrics")
    assert resp_metrics.status_code == 200
    metrics = resp_metrics.json()
    assert metrics["providers_registered_total"] >= 2
    assert metrics["zero_training_headers_injected_total"] >= 1
    assert metrics["unverified_egress_denied_total"] >= 1
