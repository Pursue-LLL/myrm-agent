"""API endpoint tests for Decoupled Async Dual-Track Content Audit & Realtime Circuit Breaker Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dual_track_content_audit_router import (
    router as dual_track_content_audit_router,
)
from app.services.security.dual_track_content_audit_service import (
    DualTrackContentAuditService,
    get_dual_track_content_audit_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = DualTrackContentAuditService()
    app = FastAPI()
    app.include_router(dual_track_content_audit_router)
    app.dependency_overrides[get_dual_track_content_audit_service] = lambda: test_service
    return TestClient(app)


def test_mirror_chunk_endpoint(client: TestClient) -> None:
    """Test POST /dual-track-audit/mirror-chunk."""
    session_id = "sess-api-001"
    # Safe chunk
    resp1 = client.post(
        "/dual-track-audit/mirror-chunk",
        json={
            "session_id": session_id,
            "sequence_no": 1,
            "text_chunk": "Welcome to our customer portal. ",
            "is_final": False,
        },
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["verdict"]["is_violation"] is False
    assert data1["is_tripped"] is False
    assert data1["circuit_breaker_signal"] is None

    # Violating chunk (credential leak)
    resp2 = client.post(
        "/dual-track-audit/mirror-chunk",
        json={
            "session_id": session_id,
            "sequence_no": 2,
            "text_chunk": "Authorization token: ghp_111122223333444455556666777788889999",
            "is_final": False,
        },
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["verdict"]["is_violation"] is True
    assert data2["is_tripped"] is True
    assert data2["circuit_breaker_signal"] is not None
    assert data2["circuit_breaker_signal"]["action"] == "TRIP_AND_ABORT"
    assert "[STREAM_ABORT_SAFETY_VIOLATION:" in data2["circuit_breaker_signal"]["abort_frame"]


def test_scan_text_endpoint(client: TestClient) -> None:
    """Test POST /dual-track-audit/scan-text."""
    # Benign scan
    resp_safe = client.post(
        "/dual-track-audit/scan-text",
        json={"text": "Everything is normal and secure."},
    )
    assert resp_safe.status_code == 200
    assert resp_safe.json()["verdict"]["is_violation"] is False

    # Violation scan
    resp_bad = client.post(
        "/dual-track-audit/scan-text",
        json={"text": "Here is the internal Q3 financial data: 未公开财报数据泄露"},
    )
    assert resp_bad.status_code == 200
    assert resp_bad.json()["verdict"]["is_violation"] is True
    assert resp_bad.json()["verdict"]["category"] == "FINANCIAL_CONFIDENTIAL"


def test_breaker_status_and_reset_endpoints(client: TestClient) -> None:
    """Test GET /sessions/{id}/breaker-status and POST /sessions/reset-breaker."""
    session_id = "sess-trip-002"

    # Trip the breaker
    client.post(
        "/dual-track-audit/mirror-chunk",
        json={
            "session_id": session_id,
            "sequence_no": 1,
            "text_chunk": "Secret: -----BEGIN PRIVATE KEY-----\nMIIEowIBAAKCAQEA",
            "is_final": False,
        },
    )

    # Check status
    status_resp = client.get(f"/dual-track-audit/sessions/{session_id}/breaker-status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_tripped"] is True
    assert status_resp.json()["signal"] is not None

    # Reset
    reset_resp = client.post(
        "/dual-track-audit/sessions/reset-breaker",
        json={"session_id": session_id},
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["was_reset"] is True

    # Check status again
    status_resp2 = client.get(f"/dual-track-audit/sessions/{session_id}/breaker-status")
    assert status_resp2.status_code == 200
    assert status_resp2.json()["is_tripped"] is False


def test_metrics_endpoint(client: TestClient) -> None:
    """Test GET /dual-track-audit/metrics."""
    resp = client.get("/dual-track-audit/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_chunks_mirrored" in data
    assert "total_violations_detected" in data
    assert "total_breakers_tripped" in data
