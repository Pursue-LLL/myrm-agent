"""Pydantic schemas for Four-Layer Memory Tri-Channel Promotion and Anti-Poisoning Audit.

[INPUT]
- None (Self-contained Pydantic schema models)

[OUTPUT]
- CapabilityMethodSchema
- RulesComplianceRequest, RulesComplianceResponse, BatchRollbackRequest, BatchRollbackResponse

[POS]
Data transfer schemas for the structured rules compliance contract and atomic anti-poisoning rollback.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
