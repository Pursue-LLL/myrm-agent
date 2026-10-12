"""Pydantic schemas for Companion Relationship Safety Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for evaluating companion dialogues and querying decorum contracts.

[POS]
- Server schemas. Exposes typed contracts for companion relationship safety, anti-exploitation, and jailbreak guard.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateCompanionInteractionRequest(BaseModel):
    """Payload to evaluate a companion conversation turn against safety rules."""

    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(..., description="User prompt text")
    candidate_response: str = Field(
        ..., description="Candidate agent response text proposed for delivery"
    )
    local_hour: int = Field(
        default=12, ge=0, le=23, description="Client local hour (0-23) for temporal boundary checks"
    )
    monetization_intent_present: bool = Field(
        default=False, description="Flag indicating presence of commercial upsell intent"
    )


class EvaluateCompanionInteractionResponse(BaseModel):
    """Verdict evaluated by the companion relationship safety guard."""

    model_config = ConfigDict(extra="forbid")

    is_safe: bool = Field(..., description="Whether interaction is compliant and safe to deliver")
    violations: list[str] = Field(
        default_factory=list,
        description="Detected violation categories (romantic_exploitation, late_night_prodding, emotional_monetization, relationship_jailbreak)",
    )
    risk_score: float = Field(..., description="Aggregated risk score (0.0 to 1.0)")
    sanitized_response: str | None = Field(
        default=None, description="Decorous sanitized response text if violation detected"
    )
    advisory_message: str | None = Field(
        default=None, description="Advisory remediation rationale for safety audit"
    )
    is_late_night: bool = Field(
        ..., description="Whether interaction occurred during late-night window (23:00-05:00)"
    )


class CompanionContractRuleDto(BaseModel):
    """Description of an individual decorum and compliance boundary rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Rule identifier code")
    category: str = Field(..., description="Violation category string")
    description: str = Field(..., description="Human-readable rule definition")
    enforcement_action: str = Field(..., description="System enforcement behavior")


class CompanionContractSummaryResponse(BaseModel):
    """Collection of active decorum boundaries and compliance redlines."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(..., description="Companion contract version")
    rules: list[CompanionContractRuleDto] = Field(
        default_factory=list, description="Active boundary rules"
    )
    late_night_window: str = Field(
        ..., description="Designated late-night rest period definition"
    )
