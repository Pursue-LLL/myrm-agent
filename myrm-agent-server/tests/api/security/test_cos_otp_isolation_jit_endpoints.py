"""API endpoint tests for CoS Sensitive OTP Isolation, Recovery Blackhole, and JIT Authorization."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.cos_otp_isolation_jit_router import (
    router as cos_otp_isolation_jit_router,
)
from app.services.security.cos_otp_isolation_jit_service import (
    CosOtpIsolationJitService,
    get_cos_otp_isolation_jit_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = CosOtpIsolationJitService()
    app = FastAPI()
    app.include_router(cos_otp_isolation_jit_router)
    app.dependency_overrides[get_cos_otp_isolation_jit_service] = lambda: test_service
    return TestClient(app)


def test_inspect_message_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/cos-otp/inspect-message",
        json={"message_text": "Security notification: Your OTP is 112233."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["redaction_count"] == 1
    assert "112233" not in data["sanitized_text"]
    assert "[REDACTED_SENSITIVE_CREDENTIAL:OTP]" in data["sanitized_text"]


def test_blackhole_check_endpoint(client: TestClient) -> None:
    # 1. Blocked reset URL
    resp_bad = client.post(
        "/cos-otp/blackhole-check",
        json={"target_text_or_url": "https://auth.corp.com/reset_password?id=999"},
    )
    assert resp_bad.status_code == 200
    assert resp_bad.json()["is_blackholed"] is True
    assert resp_bad.json()["human_intervention_required"] is True

    # 2. Allowed benign URL
    resp_good = client.post(
        "/cos-otp/blackhole-check",
        json={"target_text_or_url": "https://shop.corp.com/catalog"},
    )
    assert resp_good.status_code == 200
    assert resp_good.json()["is_blackholed"] is False


def test_jit_tickets_issue_and_consume_endpoints(client: TestClient) -> None:
    # 1. Issue ticket
    issue_resp = client.post(
        "/cos-otp/jit-tickets/issue",
        json={
            "session_id": "session-api-test",
            "target_domain": "checkout.apple.com",
            "purpose": "Device purchase confirmation",
            "otp_code": "887766",
            "validity_seconds": 120,
        },
    )
    assert issue_resp.status_code == 200
    ticket = issue_resp.json()
    ticket_id = ticket["ticket_id"]

    # 2. Consume ticket
    consume_resp = client.post(
        "/cos-otp/jit-tickets/consume",
        json={
            "ticket_id": ticket_id,
            "target_domain": "checkout.apple.com",
        },
    )
    assert consume_resp.status_code == 200
    c_data = consume_resp.json()
    assert c_data["success"] is True
    assert c_data["otp_code"] == "887766"

    # 3. Burned ticket consumption fails
    repeat_resp = client.post(
        "/cos-otp/jit-tickets/consume",
        json={
            "ticket_id": ticket_id,
            "target_domain": "checkout.apple.com",
        },
    )
    assert repeat_resp.status_code == 200
    assert repeat_resp.json()["success"] is False


def test_quota_evaluate_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/cos-otp/quota/evaluate",
        json={
            "used_units": 91.0,
            "max_units": 100.0,
            "fallback_model": "local-fallback",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "CRITICAL_90_PERCENT"
    assert data["fallback_model_recommended"] == "local-fallback"
