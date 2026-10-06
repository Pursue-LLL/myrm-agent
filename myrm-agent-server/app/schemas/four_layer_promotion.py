"""Pydantic schemas for Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.

[INPUT]
- None (Self-contained Pydantic schema models)

[OUTPUT]
- ConsolidationEventInput, ConsolidationMapRequest, CandidateStatementSchema, ConsolidationMapResponse
- ConsolidationReduceRequest, CapabilityMethodSchema, PromotionDecisionSchema, ConsolidationReduceResponse
- RulesComplianceRequest, RulesComplianceResponse, BatchRollbackRequest, BatchRollbackResponse

[POS]
Data transfer schemas for two-step Map-Reduce consolidation, tri-channel code assertions,
structured rules compliance contract, and atomic anti-poisoning rollback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConsolidationEventInput(BaseModel):
    """Raw event representation for Map phase extraction."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique event ID")
    content: str = Field(..., min_length=1, description="Event raw text content")
    failed: bool = Field(default=False, description="Whether tool execution failed")
    explicit_instruction: bool = Field(default=False, description="Whether explicit user directive")


class ConsolidationMapRequest(BaseModel):
    """Request payload to execute Map phase over single-session events."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Session identifier")
    events: list[ConsolidationEventInput] = Field(..., min_length=1, description="Raw session events")
    exposure_source: str = Field(default="internal_chat", description="'internal_chat' or 'external_untrusted'")


class CandidateStatementSchema(BaseModel):
    """Candidate statement distilled during Map phase."""

    model_config = ConfigDict(extra="forbid")

    statement: str = Field(..., description="Standalone, self-contained statement")
    supported_event_ids: list[str] = Field(..., description="Provenance event IDs")
    session_id: str = Field(..., description="Origin session ID")
    exposure_source: str = Field(..., description="Exposure source marker")
    has_tool_failure: bool = Field(..., description="Whether grounded in tool failure")
    is_explicit_user_instruction: bool = Field(..., description="Whether explicit user directive")


class ConsolidationMapResponse(BaseModel):
    """Response payload containing distilled candidates from Map phase."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Session identifier")
    candidates: list[CandidateStatementSchema] = Field(..., description="Extracted candidate statements")


class ConsolidationReduceRequest(BaseModel):
    """Request payload to execute Reduce phase across candidate statements."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateStatementSchema] = Field(..., min_length=1, description="Candidate statements")


class CapabilityMethodSchema(BaseModel):
    """Promoted capability method card."""

    model_config = ConfigDict(extra="forbid")

    method_id: str = Field(..., description="Unique method card identifier")
    title: str = Field(..., description="Method title")
    applies_when: str = Field(..., description="Execution condition context")
    method_steps: list[str] = Field(..., description="Sequential method steps")
    validation_criteria: str = Field(..., description="Validation success criteria")
    failure_signals: list[str] = Field(..., description="Failure warning signals")
    supported_event_ids: list[str] = Field(..., description="Provenance event IDs")
    promotion_channel: str = Field(..., description="Verified promotion channel")


class PromotionDecisionSchema(BaseModel):
    """Decision output detailing whether a candidate group was promoted."""

    model_config = ConfigDict(extra="forbid")

    promoted: bool = Field(..., description="Whether candidate was promoted to long-term memory")
    channel: str | None = Field(default=None, description="Promotion channel if successful")
    reason: str = Field(..., description="Decision rationale")
    method_id: str | None = Field(default=None, description="Associated method card ID if promoted")


class ConsolidationReduceResponse(BaseModel):
    """Response payload containing promoted methods and decision outcomes."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., description="Audit batch ID for lineage and rollback")
    promoted_methods: list[CapabilityMethodSchema] = Field(..., description="Promoted capability methods")
    decisions: list[PromotionDecisionSchema] = Field(..., description="Detailed promotion decisions")


class RulesComplianceRequest(BaseModel):
    """Request payload to verify response compliance against active capability rules."""

    model_config = ConfigDict(extra="forbid")

    response_text: str = Field(..., description="Output text to evaluate against active rules")


class RulesComplianceItemSchema(BaseModel):
    """Compliance verification item."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Capability rule identifier")
    statement: str = Field(..., description="Rule statement evaluated")
    compliant: bool = Field(..., description="Whether output complies with rule")
    rationale: str = Field(..., description="Compliance evaluation rationale")


class RulesComplianceResponse(BaseModel):
    """Structured compliance verification result."""

    model_config = ConfigDict(extra="forbid")

    items: list[RulesComplianceItemSchema] = Field(..., description="Per-rule compliance evaluations")
    all_compliant: bool = Field(..., description="Whether all active rules are fully satisfied")


class BatchRollbackRequest(BaseModel):
    """Request payload to atomically rollback a consolidation batch."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., min_length=1, description="Audit batch ID to rollback")


class BatchRollbackResponse(BaseModel):
    """Response payload detailing batch rollback outcome."""

    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(..., description="Rollback batch ID")
    success: bool = Field(..., description="Whether rollback succeeded")
    reverted_method_ids: list[str] = Field(..., description="List of revoked method card IDs")
