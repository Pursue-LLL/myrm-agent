"""Unit tests for InboundQuarantineService in myrm-agent-server."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.inbound_quarantine import (
    InboundQuarantineGate,
)

from app.schemas.inbound_quarantine import (
    InspectInboundMessageRequest,
)
from app.services.security.inbound_quarantine_service import (
    InboundQuarantineService,
    get_inbound_quarantine_service,
)


@pytest.fixture
def service() -> InboundQuarantineService:
    gate = InboundQuarantineGate()
    return InboundQuarantineService(gate=gate)


def test_service_inspect_clean_message(
    service: InboundQuarantineService,
) -> None:
    req = InspectInboundMessageRequest(
        content="Please review the project design proposal attached.",
        channel_type="email",
        sender="pm@company.com",
        recipient="agent@company.com",
    )
    resp = service.inspect_message(req)
    assert resp.is_quarantined is False
    assert len(resp.detected_risks) == 0
    assert resp.safe_content == req.content
    assert resp.quarantine_id is None


def test_service_inspect_sensitive_and_release(
    service: InboundQuarantineService,
) -> None:
    secret_text = "Your GitHub authentication code is: 583910. Do not share."
    req = InspectInboundMessageRequest(
        content=secret_text,
        channel_type="email",
        sender="noreply@github.com",
        recipient="dev@corp.com",
    )
    inspect_resp = service.inspect_message(req)

    # 1. Verification of physical interception
    assert inspect_resp.is_quarantined is True
    assert "OTP_2FA" in inspect_resp.detected_risks
    assert "583910" not in inspect_resp.safe_content
    assert "[SECURITY_QUARANTINE_TRIGGERED" in inspect_resp.safe_content
    assert inspect_resp.quarantine_id is not None
    qid = inspect_resp.quarantine_id

    # 2. Metadata check
    meta = service.get_record_metadata(qid)
    assert meta is not None
    assert meta.status == "ACTIVE"
    assert meta.sender == "noreply@github.com"
    assert "OTP_2FA" in meta.detected_risks

    # 3. Authorized human release
    released = service.release_quarantine(qid)
    assert released is not None
    assert released.quarantine_id == qid
    assert released.original_content == secret_text
    assert "583910" in released.original_content

    # 4. Check status transition to RELEASED
    meta_after = service.get_record_metadata(qid)
    assert meta_after is not None
    assert meta_after.status == "RELEASED"


def test_service_purge_expired(service: InboundQuarantineService) -> None:
    purge_res = service.purge_expired()
    assert purge_res.purged_count >= 0


def test_service_singleton() -> None:
    svc1 = get_inbound_quarantine_service()
    svc2 = get_inbound_quarantine_service()
    assert svc1 is svc2
