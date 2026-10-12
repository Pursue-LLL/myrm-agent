"""Service layer for Zero-Defense Error Acknowledgment and Grounded Re-Verification.

[INPUT]
- myrm_agent_harness.core.security.zero_defense_reverification::*
- app.schemas.zero_defense_reverification::*

[OUTPUT]
- ZeroDefenseReVerificationService, get_zero_defense_reverification_service

[POS]
Service coordinating dispute detection, grounded evidence cross-checking, and human expert escalations.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.zero_defense_reverification import (
    DisputeDetectionResult,
    EvidenceCitation,
    ExpertEscalationTicket,
    GroundedReVerificationResult,
    ZeroDefenseReVerificationEngine,
)

from app.schemas.zero_defense_reverification import (
    CreateEscalationTicketRequest,
    CrossCheckRequest,
    CrossCheckResponse,
    DetectDisputeRequest,
    DetectDisputeResponse,
    EscalationTicketResponse,
    EvidenceCitationSchema,
    ResolveEscalationTicketRequest,
)

logger = logging.getLogger(__name__)


def _to_schema_citation(c: EvidenceCitation) -> EvidenceCitationSchema:
    return EvidenceCitationSchema(
        source_path=c.source_path,
        line_or_location=c.line_or_location,
        quote_snippet=c.quote_snippet,
    )


def _to_domain_citation(s: EvidenceCitationSchema) -> EvidenceCitation:
    return EvidenceCitation(
        source_path=s.source_path,
        line_or_location=s.line_or_location,
        quote_snippet=s.quote_snippet,
    )


def _to_detect_response(r: DisputeDetectionResult) -> DetectDisputeResponse:
    return DetectDisputeResponse(
        is_dispute=r.is_dispute,
        intent_type=r.intent_type.value if r.intent_type else None,
        dispute_anchor=r.dispute_anchor,
        mandatory_protocol_phrase=r.mandatory_protocol_phrase,
    )


def _to_cross_check_response(r: GroundedReVerificationResult) -> CrossCheckResponse:
    return CrossCheckResponse(
        dispute_anchor=r.dispute_anchor,
        prior_conclusion=r.prior_conclusion,
        evidence_citations=[_to_schema_citation(c) for c in r.evidence_citations],
        verdict=r.verdict.value,
        requires_expert_escalation=r.requires_expert_escalation,
        correction_explanation=r.correction_explanation,
    )


def _to_ticket_response(t: ExpertEscalationTicket) -> EscalationTicketResponse:
    return EscalationTicketResponse(
        ticket_id=t.ticket_id,
        session_id=t.session_id,
        risk_domain=t.risk_domain,
        dispute_summary=t.dispute_summary,
        prior_conclusion=t.prior_conclusion,
        evidence_citations=[_to_schema_citation(c) for c in t.evidence_citations],
        created_at=t.created_at,
        status=t.status,
        resolution_notes=t.resolution_notes,
    )


class ZeroDefenseReVerificationService:
    """Service governing zero-defense protocols and grounded truth verification."""

    def __init__(self, engine: ZeroDefenseReVerificationEngine | None = None) -> None:
        self._engine: ZeroDefenseReVerificationEngine = engine or ZeroDefenseReVerificationEngine()

    def detect_dispute(self, req: DetectDisputeRequest) -> DetectDisputeResponse:
        """Detect dispute or accusation signals and enforce zero-defense acknowledgment."""
        res = self._engine.detect_dispute_intent(req.user_utterance)
        return _to_detect_response(res)

    def cross_check(self, req: CrossCheckRequest) -> CrossCheckResponse:
        """Execute grounded side-by-side comparison between prior conclusion and citations."""
        domain_citations = [_to_domain_citation(c) for c in req.citations]
        res = self._engine.verify_and_cross_check(
            dispute_anchor=req.dispute_anchor,
            prior_conclusion=req.prior_conclusion,
            citations=domain_citations,
            high_risk_domain=req.high_risk_domain,
        )
        return _to_cross_check_response(res)

    def create_escalation_ticket(self, req: CreateEscalationTicketRequest) -> EscalationTicketResponse:
        """Open an escalation ticket for domain expert arbitration."""
        domain_citations = [_to_domain_citation(c) for c in req.citations]
        ticket = self._engine.create_expert_escalation(
            session_id=req.session_id,
            risk_domain=req.risk_domain,
            dispute_summary=req.dispute_summary,
            prior_conclusion=req.prior_conclusion,
            citations=domain_citations,
        )
        return _to_ticket_response(ticket)

    def get_escalation_ticket(self, ticket_id: str) -> EscalationTicketResponse | None:
        """Fetch escalation ticket by ID."""
        t = self._engine.get_escalation_ticket(ticket_id)
        if t is None:
            return None
        return _to_ticket_response(t)

    def resolve_escalation_ticket(
        self,
        ticket_id: str,
        req: ResolveEscalationTicketRequest,
    ) -> EscalationTicketResponse:
        """Resolve an escalation ticket with expert arbitration verdict."""
        t = self._engine.resolve_escalation_ticket(ticket_id, req.resolution_notes)
        return _to_ticket_response(t)

    def reset_all(self) -> None:
        """Reset internal tickets (test isolation)."""
        self._engine.reset_all()


_INSTANCE: ZeroDefenseReVerificationService | None = None


def get_zero_defense_reverification_service() -> ZeroDefenseReVerificationService:
    """Return singleton instance of ZeroDefenseReVerificationService."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ZeroDefenseReVerificationService()
    return _INSTANCE
