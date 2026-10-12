"""Pydantic schemas for Agent Authority ChangeGuard review decision lanes and evidence hardening.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for evaluating change proposals across Lane A (gates) and Lane B (reviews).

[POS]
- Server schemas for SafeAI ChangeGuard WS1-WS5 compliance.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvidenceRecordDto(BaseModel):
    """Hardened evidence metadata backing a finding claim."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str = Field(
        ...,
        description="Evidence type taxonomy: static_config, static_pattern, runtime_observed",
    )
    source_file: str = Field(..., description="Source path of evidence artifact")
    line_number: int | None = Field(default=None, description="Optional line number")
    pattern_matched: str | None = Field(
        default=None, description="Optional regex or configuration pattern matched"
    )
    sha256_digest: str | None = Field(
        default=None, description="Optional cryptographic digest of the verified artifact"
    )
    description: str = Field(default="", description="Descriptive context")


class HardenedFindingDto(BaseModel):
    """Security or governance finding with hardened evidence."""

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(..., description="Unique finding identifier")
    rule_id: str = Field(..., description="Rule identifier (e.g. PROMPT_*, TOOL_*, SKILL_*)")
    category: str = Field(..., description="Governance or risk category")
    target_object: str = Field(..., description="Affected object or file path")
    change_class: str = Field(
        default="LOW_CHANGE",
        description="Materiality class: NO_CHANGE, LOW_CHANGE, MATERIAL_CHANGE, HIGH_RISK_CHANGE, UNKNOWN",
    )
    provenance_class: str = Field(
        default="detected",
        description="Evidence provenance: declared, detected, inferred, unknown",
    )
    gateability: str = Field(
        default="deterministic",
        description="Gateability: deterministic (trips Lane A) or review_only (trips Lane B)",
    )
    evidence: EvidenceRecordDto = Field(..., description="Hardened evidence record")
    message: str = Field(..., description="Human-readable finding explanation")


class ChangeGuardExceptionDto(BaseModel):
    """File-backed exception record (.myrm/exceptions.yml)."""

    model_config = ConfigDict(extra="forbid")

    exception_id: str = Field(..., description="Unique exception ID")
    finding_or_rule_id: str = Field(
        ..., description="Target finding ID, rule ID, or wildcard pattern"
    )
    scope: str = Field(..., description="Scope path pattern or wildcard")
    risk_owner: str = Field(..., description="Named security or product owner accountable")
    rationale: str = Field(..., description="Technical justification for exemption")
    compensating_controls: str = Field(..., description="Compensating safety controls")
    expires_at: str = Field(..., description="ISO timestamp when exception expires")
    review_trigger: str = Field(default="manual", description="Trigger for re-review")


class LaneDecisionSummaryDto(BaseModel):
    """Decision summary for a distinct review lane."""

    model_config = ConfigDict(extra="forbid")

    lane: str = Field(..., description="Lane identifier (lane_a or lane_b)")
    outcome: str = Field(
        ..., description="Canonical outcome: pass, warn, review_required, block"
    )
    findings: list[HardenedFindingDto] = Field(
        default_factory=list, description="Findings assigned to this lane"
    )
    unresolved_questions: list[str] = Field(
        default_factory=list, description="Mandatory human review questions"
    )


class EvaluateChangesRequest(BaseModel):
    """Payload to evaluate a batch of change findings across ChangeGuard lanes."""

    model_config = ConfigDict(extra="forbid")

    findings: list[HardenedFindingDto] = Field(
        default_factory=list, description="List of hardened findings to evaluate"
    )
    exceptions: list[ChangeGuardExceptionDto] = Field(
        default_factory=list, description="Registered exceptions to apply"
    )
    fail_on_authority_change: str | None = Field(
        default=None,
        description="Authority change threshold (MATERIAL_CHANGE or HIGH_RISK_CHANGE)",
    )
    enforce_definition_review_floor: bool = Field(
        default=True,
        description="Whether to enforce review floor on prompt/tool/skill definitions",
    )
    strict_exceptions: bool = Field(
        default=False,
        description="Whether stale or expired exceptions cause evaluation failure",
    )
    current_time_iso: str | None = Field(
        default=None, description="Optional ISO timestamp to evaluate expiration against"
    )


class EvaluateChangesResponse(BaseModel):
    """Result of ChangeGuard evaluation with separated lanes."""

    model_config = ConfigDict(extra="forbid")

    overall_outcome: str = Field(
        ..., description="Consolidated outcome (pass, warn, review_required, block)"
    )
    lane_a: LaneDecisionSummaryDto = Field(
        ..., description="Lane A automated deterministic gate verdict"
    )
    lane_b: LaneDecisionSummaryDto = Field(
        ..., description="Lane B mandatory human governance review questions"
    )
    highest_change_class: str = Field(..., description="Highest materiality class detected")
    applied_exceptions: list[str] = Field(
        default_factory=list, description="Exception IDs successfully applied"
    )
    stale_or_expired_exceptions: list[str] = Field(
        default_factory=list, description="Exception IDs detected as expired or stale"
    )


class ChangeGuardConfigSummary(BaseModel):
    """Configuration summary of supported ChangeGuard standards."""

    model_config = ConfigDict(extra="forbid")

    supported_change_classes: list[str] = Field(..., description="Materiality classes")
    supported_provenance_classes: list[str] = Field(..., description="Provenance classes")
    supported_evidence_types: list[str] = Field(..., description="Evidence types")
    definition_prefixes: list[str] = Field(..., description="Definition rule prefixes")
