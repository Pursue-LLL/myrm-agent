"""Unit tests for Runtime Environment and Connection Integrity Attestation endpoints.

[POS]
Validates retrieval of the all-vector attestation report (WebUI trust badge status)
and on-demand manual verification refresh via security API.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.attestation_router import router as attestation_router
from app.services.security.attestation_service import AttestationService


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing dedicated test client mounting attestation router."""
    test_app = FastAPI(title="Security Attestation Test App")
    test_app.include_router(attestation_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_attestation_cache() -> None:
    """Clear cached attestation reports before each test."""
    AttestationService.clear_cache()


@pytest.mark.asyncio
async def test_get_runtime_attestation_report_success(client) -> None:
    """Ensure GET /security/attestation returns complete all-vector attestation report."""
    resp = client.get("/api/v1/security/attestation")
    assert resp.status_code == 200
    data = resp.json()

    assert data["attestation_id"].startswith("attest-")
    assert isinstance(data["overall_passed"], bool)
    assert data["host_fingerprint"] != ""
    assert isinstance(data["vector_results"], list)
    assert len(data["vector_results"]) >= 1

    # Check vector result schema
    first_vec = data["vector_results"][0]
    assert "vector" in first_vec
    assert "target" in first_vec
    assert "is_valid" in first_vec
    assert "severity" in first_vec


@pytest.mark.asyncio
async def test_post_verify_runtime_attestation_success(client) -> None:
    """Ensure POST /security/attestation/verify forces a fresh on-demand attestation."""
    resp = client.post("/api/v1/security/attestation/verify")
    assert resp.status_code == 200
    data = resp.json()

    assert data["attestation_id"].startswith("attest-")
    assert data["overall_passed"] is True
    assert "certified valid" in data["summary"].lower() or "anomaly" in data["summary"].lower()
