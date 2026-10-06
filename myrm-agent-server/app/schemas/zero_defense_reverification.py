"""Pydantic schemas for Zero-Defense Error Acknowledgment and Grounded Re-Verification.

[INPUT]
- None (Self-contained schema representations for zero-defense error handling)

[OUTPUT]
- DetectDisputeRequest, DetectDisputeResponse, ReverificationEvidenceRequest, ReverificationEvidenceResponse

[POS]
- app.schemas.zero_defense_reverification
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DetectDisputeRequest(BaseModel):
    """Payload to detect user objection, dispute, or error accusation."""

    model_config = ConfigDict(extra="forbid")

    user_utterance: str = Field(..., min_length=1, max_length=4000, description="Raw user input text")


class DetectDisputeResponse(BaseModel):
    """Result of dispute intent detection with mandatory zero-defense phrase."""

    model_config = ConfigDict(extra="forbid")

    is_dispute: bool = Field(..., description="Whether user expresses objection or error accusation")
    intent_type: str | None = Field(default=None, description="Type: FACTUAL_ERROR, CALCULATION_ERROR, etc.")
    dispute_anchor: str = Field(..., description="Matched keyword or segment triggering dispute")
    mandatory_protocol_phrase: str = Field(..., description="Non-defensive acknowledgement phrase")


class EvidenceCitationSchema(BaseModel):
    """Grounded evidence citation referencing exact file and position."""

    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(..., min_length=1, max_length=512, description="Source file path or URI")
    line_or_location: str = Field(..., min_length=1, max_length=128, description="Line number or section anchor")
    quote_snippet: str = Field(..., min_length=1, max_length=2000, description="Exact excerpt or snippet")


class CrossCheckRequest(BaseModel):
    """Request payload to cross-check disputed claim against grounded evidence."""

    model_config = ConfigDict(extra="forbid")

    dispute_anchor: str = Field(..., min_length=1, max_length=256, description="Anchor phrase under dispute")
    prior_conclusion: str = Field(..., min_length=1, max_length=2000, description="Previous output or claim")
    citations: list[EvidenceCitationSchema] = Field(
        default_factory=list,
        description="Freshly gathered evidence citations",
    )
    high_risk_domain: str | None = Field(
        default=None,
        description="High-risk classification domain: legal, medical, finance, etc.",
    )


class CrossCheckResponse(BaseModel):
    """Side-by-side grounded verification output."""

    model_config = ConfigDict(extra="forbid")

    dispute_anchor: str
    prior_conclusion: str
    evidence_citations: list[EvidenceCitationSchema]
    verdict: str = Field(..., description="Verdict: CORRECTED, CONFIRMED_USER_CORRECT, AMBIGUOUS_ESCALATE, etc.")
    requires_expert_escalation: bool
    correction_explanation: str


class CreateEscalationTicketRequest(BaseModel):
    """Payload to open a human expert arbitration ticket."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, max_length=64, description="Session ID")
    risk_domain: str = Field(..., min_length=1, max_length=64, description="Domain: legal, finance, etc.")
    dispute_summary: str = Field(..., min_length=1, max_length=2000, description="Summary of the conflict")
    prior_conclusion: str = Field(..., min_length=1, max_length=2000, description="Prior disputed conclusion")
    citations: list[EvidenceCitationSchema] = Field(default_factory=list)


class ResolveEscalationTicketRequest(BaseModel):
    """Payload to record an expert arbitration verdict."""

    model_config = ConfigDict(extra="forbid")

    resolution_notes: str = Field(..., min_length=1, max_length=2000, description="Arbitration findings and verdict")


class EscalationTicketResponse(BaseModel):
    """Details of an expert escalation ticket."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    session_id: str
    risk_domain: str
    dispute_summary: str
    prior_conclusion: str
    evidence_citations: list[EvidenceCitationSchema]
    created_at: float
    status: str
    resolution_notes: str | None = None
