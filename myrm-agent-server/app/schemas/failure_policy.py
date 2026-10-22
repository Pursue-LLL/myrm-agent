"""Pydantic V2 schemas for Per-Role Subagent Failure Restart & Redeploy Policy (Item 35).

[INPUT]
- RegisterRoleFailurePolicyRequest, ReportFailureEventRequest, and session identifiers.

[OUTPUT]
- Strongly-typed DTOs for declarative failure policies, autonomous remediation decisions,
  and failure history records.

[POS]
- Server-side typed contracts for role-bound mid-task crash recovery and autonomous escalation.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class FailureActionEnum(enum.StrEnum):
    """Remediation actions executable by the orchestrator."""

    RESTART_FRESH = "restart_fresh"
    REDEPLOY_SPECS = "redeploy_specs"
    ESCALATE_PARENT = "escalate_parent"
    SKIP = "skip"


class FailureTriggerReasonEnum(enum.StrEnum):
    """Categorized triggers for subagent failures."""

    CRASH_ERROR = "crash_error"
    STUCK_TIMEOUT = "stuck_timeout"
    OUTPUT_SPEC_MISMATCH = "output_spec_mismatch"
    TOOL_QUOTA_EXHAUSTED = "tool_quota_exhausted"


class RegisterRoleFailurePolicyRequest(BaseModel):
    """Request payload to declare a failure policy for a specific role."""

    model_config = ConfigDict(frozen=True)

    role_key: str = Field(..., min_length=1, description="Subagent role identifier")
    primary_action: FailureActionEnum = Field(
        default=FailureActionEnum.RESTART_FRESH,
        description="First-line remediation action",
    )
    allow_failure: bool = Field(
        default=False,
        description="If true, allows non-fatal failure to be skipped",
    )
    max_retries: int = Field(default=2, ge=0, le=10, description="Max consecutive retry attempts")
    fallback_action: FailureActionEnum = Field(
        default=FailureActionEnum.ESCALATE_PARENT,
        description="Action when max retries exceeded",
    )
    fresh_instructions_template: str = Field(
        default="",
        description="Custom prompt guidance for restart",
    )
    redeploy_model_tier_downgrade: bool = Field(
        default=False,
        description="Whether to downgrade model tier on redeploy",
    )


class RoleFailurePolicyDTO(BaseModel):
    """Active declarative failure policy bound to a role."""

    model_config = ConfigDict(frozen=True)

    role_key: str
    primary_action: FailureActionEnum
    allow_failure: bool
    max_retries: int
    fallback_action: FailureActionEnum
    fresh_instructions_template: str
    redeploy_model_tier_downgrade: bool


class ReportFailureEventRequest(BaseModel):
    """Request payload reporting a subagent failure to trigger autonomous remediation."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., min_length=1, description="Unique subagent task identifier")
    role_key: str = Field(..., min_length=1, description="Role identifier of the failed worker")
    trigger_reason: FailureTriggerReasonEnum = Field(
        ...,
        description="Categorized root cause of the failure",
    )
    error_message: str = Field(..., min_length=1, description="Descriptive error detail")
    event_id: str | None = Field(None, description="Optional custom event identifier")


class PolicyEvaluationDecisionDTO(BaseModel):
    """Autonomous remediation decision produced by evaluating a failure against role policy."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    task_id: str
    role_key: str
    action: FailureActionEnum
    attempt_number: int
    max_retries: int
    rationale: str
    redeploy_payload: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class RolePolicyListResponse(BaseModel):
    """Collection of all declared role failure policies in the session."""

    model_config = ConfigDict(frozen=True)

    policies: list[RoleFailurePolicyDTO]
    total_count: int


class PolicyHistoryResponse(BaseModel):
    """Historical timeline of autonomous remediation decisions."""

    model_config = ConfigDict(frozen=True)

    history: list[PolicyEvaluationDecisionDTO]
    total_count: int
