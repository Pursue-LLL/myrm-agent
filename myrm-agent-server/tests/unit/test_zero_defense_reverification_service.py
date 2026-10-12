"""Unit test suite for ZeroDefenseReVerificationService."""

from __future__ import annotations

import pytest

from app.schemas.zero_defense_reverification import (
    CreateEscalationTicketRequest,
    CrossCheckRequest,
    DetectDisputeRequest,
    EvidenceCitationSchema,
    ResolveEscalationTicketRequest,
)
from app.services.security.zero_defense_reverification_service import (
    ZeroDefenseReVerificationService,
)


@pytest.fixture
def service() -> ZeroDefenseReVerificationService:
    svc = ZeroDefenseReVerificationService()
    svc.reset_all()
    return svc


def test_detect_dispute_calculation_signal(service: ZeroDefenseReVerificationService) -> None:
    req = DetectDisputeRequest(user_utterance="你算错了，第4项成本加总完全不对！")
    res = service.detect_dispute(req)
    assert res.is_dispute is True
    assert res.intent_type == "CALCULATION_ERROR"
    assert "重新核查" in res.mandatory_protocol_phrase


def test_detect_dispute_no_signal(service: ZeroDefenseReVerificationService) -> None:
    req = DetectDisputeRequest(user_utterance="请为我列出下周的工作待办清单。")
    res = service.detect_dispute(req)
    assert res.is_dispute is False
    assert res.intent_type is None
    assert res.mandatory_protocol_phrase == ""


def test_cross_check_fail_closed_on_empty_citations(
    service: ZeroDefenseReVerificationService,
) -> None:
    req = CrossCheckRequest(
        dispute_anchor="Q4 Gross Margin",
        prior_conclusion="Margin reached 45%",
        citations=[],
    )
    res = service.cross_check(req)
    assert res.verdict == "AMBIGUOUS_ESCALATE"
    assert res.requires_expert_escalation is True
    assert "无法原地证实" in res.correction_explanation


def test_cross_check_with_grounded_evidence(service: ZeroDefenseReVerificationService) -> None:
    req = CrossCheckRequest(
        dispute_anchor="Contract indemnity liability cap",
        prior_conclusion="Unlimited indemnification",
        citations=[
            EvidenceCitationSchema(
                source_path="legal/vendor_agreement.pdf",
                line_or_location="Section 12.2",
                quote_snippet="Total aggregate liability shall not exceed fees paid in prior 12 months.",
            )
        ],
        high_risk_domain="legal",
    )
    res = service.cross_check(req)
    assert res.verdict == "CONFIRMED_USER_CORRECT"
    assert res.requires_expert_escalation is True
    assert "vendor_agreement.pdf" in res.correction_explanation


def test_escalation_ticket_service_lifecycle(service: ZeroDefenseReVerificationService) -> None:
    create_req = CreateEscalationTicketRequest(
        session_id="sess-enterprise-01",
        risk_domain="legal",
        dispute_summary="Dispute regarding non-compete clause duration",
        prior_conclusion="Non-compete extends to 5 years globally",
        citations=[
            EvidenceCitationSchema(
                source_path="policies/employment.pdf",
                line_or_location="p.4",
                quote_snippet="Non-compete duration is strictly 1 year within state boundaries.",
            )
        ],
    )
    ticket = service.create_escalation_ticket(create_req)
    assert ticket.ticket_id.startswith("esc-")
    assert ticket.status == "OPEN"
    assert len(ticket.evidence_citations) == 1

    queried = service.get_escalation_ticket(ticket.ticket_id)
    assert queried is not None
    assert queried.ticket_id == ticket.ticket_id

    resolved = service.resolve_escalation_ticket(
        ticket.ticket_id,
        ResolveEscalationTicketRequest(resolution_notes="Legal counsel confirmed 1 year restriction limit."),
    )
    assert resolved.status == "RESOLVED"
    assert resolved.resolution_notes == "Legal counsel confirmed 1 year restriction limit."
