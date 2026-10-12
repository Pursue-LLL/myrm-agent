"""Pydantic schemas for Pre-Action Side-Effect Gate and Post-Run Acceptance.

[INPUT]
None.

[OUTPUT]
DTO models for pre-action challenges, decisions, execution receipts, and deterministic acceptance.

[POS]
Server schemas. Exposes typed contracts for frontend and external APIs to inspect
intercepted high-risk tools and execute post-run deliverable quality assurance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PreActionChallengeDto(BaseModel):
    """Intercepted pre-action challenge details."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(..., description="Unique challenge identifier")
    session_id: str = Field(..., description="Associated session or task ID")
    tool_name: str = Field(..., description="Name of the intercepted tool")
    arguments: dict[str, str | int | float | bool | None | list[str] | dict[str, str]] = Field(
        default_factory=dict, description="Intercepted tool parameters"
    )
    idempotency_key: str = Field(..., description="Deterministic idempotency key")
    risk_level: str = Field(..., description="Assessed risk level: low, medium, high, critical")
    summary: str = Field(..., description="Human-readable explanation of the intercepted action")
    created_at: float = Field(..., description="Epoch timestamp of interception")
    expires_at: float = Field(..., description="Epoch timestamp of challenge expiration")


class PreActionDecisionRequest(BaseModel):
    """Decision request payload for intercepted challenge."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"] = Field(..., description="Approval decision")
    reviewer_id: str = Field(..., description="Identifier of the human reviewer")
    reason: str | None = Field(default=None, description="Optional justification or rejection cause")


class PreActionDecisionResponse(BaseModel):
    """Decision response returning token or denial status."""

    model_config = ConfigDict(extra="forbid")

    challenge_id: str = Field(..., description="Challenge identifier")
    status: str = Field(..., description="Resulting status: approved, rejected, expired")
    auth_token: str | None = Field(default=None, description="Single-use authorization token if approved")
    message: str = Field(..., description="Status summary message")


class ActionReceiptDto(BaseModel):
    """Immutable record of executed external action."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(..., description="Deterministic idempotency key")
    tool_name: str = Field(..., description="Name of executed tool")
    provider_receipt_id: str = Field(..., description="External vendor transaction/message ID")
    status: str = Field(..., description="Execution status")
    output_summary: str = Field(..., description="Brief outcome summary")
    challenge_id: str | None = Field(default=None, description="Associated challenge ID if intercepted")
    recorded_at: float = Field(..., description="Epoch timestamp when recorded")


class ActionReceiptCreateRequest(BaseModel):
    """Request to record a new external execution receipt."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(..., description="Deterministic idempotency key")
    tool_name: str = Field(..., description="Name of executed tool")
    provider_receipt_id: str = Field(..., description="External vendor receipt identifier")
    output_summary: str = Field(..., description="Brief outcome summary")
    challenge_id: str | None = Field(default=None, description="Associated challenge ID")


class AcceptanceRuleDto(BaseModel):
    """Deterministic post-run quality rule specification."""

    model_config = ConfigDict(extra="forbid")

    rule_type: Literal[
        "non_empty",
        "length_bounds",
        "required_structure",
        "required_json_keys",
        "numerical_sum_equals",
    ] = Field(..., description="Rule category")
    description: str = Field(..., description="Rule description")
    min_length: int | None = Field(default=None, description="Minimum allowed text length")
    max_length: int | None = Field(default=None, description="Maximum allowed text length")
    required_sections: list[str] | None = Field(default=None, description="Required markdown sections")
    required_json_keys: list[str] | None = Field(default=None, description="Required JSON top-level keys")
    sum_field_names: list[str] | None = Field(default=None, description="Item fields to aggregate")
    total_field_name: str | None = Field(default=None, description="Total field name to compare against")


class AcceptanceEvaluationRequest(BaseModel):
    """Request payload for running post-run acceptance evaluation."""

    model_config = ConfigDict(extra="forbid")

    text_content: str | None = Field(default=None, description="Markdown/text deliverable")
    structured_payload: (
        dict[
            str,
            str
            | int
            | float
            | bool
            | None
            | list[dict[str, float | str | int]]
            | list[str]
            | list[float]
            | dict[str, str | float | int],
        ]
        | None
    ) = Field(default=None, description="Structured JSON deliverable")
    rules: list[AcceptanceRuleDto] = Field(..., description="Deterministic acceptance rules")


class AcceptanceViolationDto(BaseModel):
    """Specific acceptance rule failure."""

    model_config = ConfigDict(extra="forbid")

    rule_type: str = Field(..., description="Violated rule type")
    message: str = Field(..., description="Violation message")
    actual_value: str | int | float | None = Field(default=None, description="Offending value observed")


class AcceptanceEvaluationResponse(BaseModel):
    """Post-run deterministic acceptance evaluation report."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if deliverable satisfied all acceptance rules")
    summary: str = Field(..., description="Overall acceptance verdict summary")
    violations: list[AcceptanceViolationDto] = Field(default_factory=list, description="List of rule violations")
    evaluated_at: float = Field(..., description="Evaluation epoch timestamp")
