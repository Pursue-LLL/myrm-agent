"""Unit tests for CosOtpIsolationJitService."""

from __future__ import annotations

import pytest

from app.schemas.cos_otp_isolation_jit import (
    BlackholeCheckRequest,
    ConsumeJitTicketRequest,
    EvaluateQuotaRequest,
    InspectMessageOtpRequest,
    IssueJitTicketRequest,
)
from app.services.security.cos_otp_isolation_jit_service import (
    CosOtpIsolationJitService,
    get_cos_otp_isolation_jit_service,
)


@pytest.fixture
def service() -> CosOtpIsolationJitService:
    return CosOtpIsolationJitService()


def test_singleton_getter() -> None:
    svc1 = get_cos_otp_isolation_jit_service()
    svc2 = get_cos_otp_isolation_jit_service()
    assert svc1 is svc2


def test_inspect_message_otps(service: CosOtpIsolationJitService) -> None:
    req = InspectMessageOtpRequest(
        message_text="Bank update: your verification code is 789456. Do not share."
    )
    res = service.inspect_message_otps(req)
    assert res.redaction_count == 1
    assert "789456" in res.detected_otp_codes
    assert "789456" not in res.sanitized_text
    assert "[REDACTED_SENSITIVE_CREDENTIAL:OTP]" in res.sanitized_text


def test_check_recovery_blackhole(service: CosOtpIsolationJitService) -> None:
    # 1. Recovery link
    req_dangerous = BlackholeCheckRequest(
        target_text_or_url="https://secure.example.com/auth/password-reset?key=token123"
    )
    res_dangerous = service.check_recovery_blackhole(req_dangerous)
    assert res_dangerous.is_blackholed is True
    assert res_dangerous.human_intervention_required is True
    assert "blackhole lock engaged" in res_dangerous.reason

    # 2. Benign link
    req_safe = BlackholeCheckRequest(target_text_or_url="https://docs.myrmidon.ai/getting-started")
    res_safe = service.check_recovery_blackhole(req_safe)
    assert res_safe.is_blackholed is False
    assert res_safe.human_intervention_required is False


def test_jit_ticket_lifecycle(service: CosOtpIsolationJitService) -> None:
    issue_req = IssueJitTicketRequest(
        session_id="session-user-777",
        target_domain="shop.merchant.com",
        purpose="Purchase authorization",
        otp_code="321654",
        validity_seconds=180,
    )
    ticket_resp = service.issue_jit_ticket(issue_req)
    assert ticket_resp.session_id == "session-user-777"
    assert ticket_resp.consumed is False

    # 1. Successful consumption
    consume_req = ConsumeJitTicketRequest(
        ticket_id=ticket_resp.ticket_id,
        target_domain="shop.merchant.com",
    )
    consume_res = service.consume_jit_ticket(consume_req)
    assert consume_res.success is True
    assert consume_res.otp_code == "321654"

    # 2. Re-consumption rejected (burn after reading)
    second_consume = service.consume_jit_ticket(consume_req)
    assert second_consume.success is False
    assert second_consume.otp_code is None


def test_evaluate_quota_watermarks(service: CosOtpIsolationJitService) -> None:
    # 1. Elevated 75%
    req_75 = EvaluateQuotaRequest(used_units=780.0, max_units=1000.0)
    res_75 = service.evaluate_quota(req_75)
    assert res_75.tier == "ELEVATED_75_PERCENT"
    assert "75%" in (res_75.alert_message or "")
    assert res_75.fallback_model_recommended == "llama-3.1-8b-local"

    # 2. Critical 90%
    req_90 = EvaluateQuotaRequest(used_units=950.0, max_units=1000.0)
    res_90 = service.evaluate_quota(req_90)
    assert res_90.tier == "CRITICAL_90_PERCENT"
    assert "90%" in (res_90.alert_message or "")
