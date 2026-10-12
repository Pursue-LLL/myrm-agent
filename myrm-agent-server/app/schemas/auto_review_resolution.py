"""
[POS] app/schemas/auto_review_resolution.py
[INPUT] pydantic, enum
[OUTPUT] DenialReasonCodeEnum, ResolutionBranchEnum, HandoverStatusEnum, ReportDenialRequest, DenialDiagnosticResponse, BranchEvaluationRequest, BranchEvaluationResponse, StageHandoverRequest, HandoverDeckResponse, CommitResolutionRequest, ResolutionDecisionResponse, AutoReviewResolutionMetricsResponse

Pydantic schemas for Auto-Review Denial Four-Way Adaptive Resolution State Machine Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DenialReasonCodeEnum(StrEnum):
    """Normalized diagnostic reason classification for security auto-review block."""

    POLICY_VIOLATION = "POLICY_VIOLATION"
    UNAUTHORIZED_PATH = "UNAUTHORIZED_PATH"
    SENSITIVE_DATA_LEAK = "SENSITIVE_DATA_LEAK"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    HIGH_RISK_ACTION = "HIGH_RISK_ACTION"
    SANDBOX_ISOLATION_BREACH = "SANDBOX_ISOLATION_BREACH"


class ResolutionBranchEnum(StrEnum):
    """Four-way adaptive resolution strategies inspired by Dots protocol."""

    ASK_USER = "ASK_USER"
    TRY_ALTERNATIVE = "TRY_ALTERNATIVE"
    HANDOVER_TO_USER = "HANDOVER_TO_USER"
    STOP_OPERATION = "STOP_OPERATION"


class HandoverStatusEnum(StrEnum):
    """Lifecycle status for human handover deck."""

    STAGED = "STAGED"
    EXECUTED_BY_USER = "EXECUTED_BY_USER"
    DISMISSED_BY_USER = "DISMISSED_BY_USER"
    EXPIRED = "EXPIRED"


class ReportDenialRequest(BaseModel):
    """Payload to report and register a security auto-review block."""

    session_id: str = Field(..., min_length=1, description="Agent execution session identifier")
    blocked_action: str = Field(..., min_length=1, description="Action or tool intercepted")
    denial_reason: str = Field(..., min_length=1, description="Explanation of why action was blocked")
    reason_code: DenialReasonCodeEnum = Field(..., description="Normalized denial taxonomy code")
    policy_rule_id: str = Field(..., min_length=1, description="Policy rule or gate identifier")
    context_data: dict[str, str] = Field(default_factory=dict, description="Contextual key-value pairs")
    custom_alternatives: list[str] | None = Field(default=None, description="Optional manual alternatives override")
    custom_suggested_branch: ResolutionBranchEnum | None = Field(default=None, description="Optional manual branch suggestion override")


class DenialDiagnosticResponse(BaseModel):
    """Structured diagnostic report injected back into agent reflection loop."""

    diagnostic_id: str = Field(..., description="Unique diagnostic event identifier")
    blocked_action: str = Field(..., description="Action blocked")
    denial_reason: str = Field(..., description="Denial reason")
    reason_code: DenialReasonCodeEnum = Field(..., description="Taxonomy code")
    policy_rule_id: str = Field(..., description="Policy identifier")
    allowed_alternatives: list[str] = Field(..., description="Suggested lower-privilege alternative actions")
    suggested_branch: ResolutionBranchEnum = Field(..., description="Recommended resolution branch")
    context_data: dict[str, str] = Field(default_factory=dict, description="Context data")
    timestamp: float = Field(..., description="Epoch timestamp")


class BranchEvaluationRequest(BaseModel):
    """Payload to evaluate proposed resolution branch against loop breakers."""

    session_id: str = Field(..., min_length=1, description="Agent session identifier")
    proposed_branch: ResolutionBranchEnum = Field(..., description="Agent's proposed next branch")


class BranchEvaluationResponse(BaseModel):
    """Evaluation result indicating permissible branch or forced diversion."""

    effective_branch: ResolutionBranchEnum = Field(..., description="Permitted or diverted branch")
    explanation: str = Field(..., description="Evaluation justification")
    loop_breaker_triggered: bool = Field(..., description="True if loop breaker forced diversion")


class StageHandoverRequest(BaseModel):
    """Payload to pre-stage an interactive human execution handover card."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    task_description: str = Field(..., min_length=1, description="Description of the goal")
    prepared_command: str = Field(..., min_length=1, description="Pre-composed executable shell/API command")
    parameters: dict[str, str] = Field(default_factory=dict, description="Pre-filled parameters")
    guidance_notes: str = Field(default="", description="Operator guidance instructions")


class HandoverDeckResponse(BaseModel):
    """Staged contextual card presented to human user for one-click release."""

    handover_id: str = Field(..., description="Unique handover card identifier")
    session_id: str = Field(..., description="Session identifier")
    task_description: str = Field(..., description="Task narrative")
    prepared_command: str = Field(..., description="Prepared command")
    parameters: dict[str, str] = Field(default_factory=dict, description="Parameters map")
    guidance_notes: str = Field(..., description="Operator guidance")
    created_at: float = Field(..., description="Creation epoch timestamp")
    status: HandoverStatusEnum = Field(..., description="Deck lifecycle status")
    executed_at: float | None = Field(default=None, description="Execution epoch timestamp if released")


class CommitResolutionRequest(BaseModel):
    """Payload to record agent's final decision for current denial."""

    session_id: str = Field(..., min_length=1, description="Session identifier")
    chosen_branch: ResolutionBranchEnum = Field(..., description="Chosen resolution branch")
    rationale: str = Field(..., min_length=1, description="Agent reasoning explanation")
    alternative_attempted: str | None = Field(default=None, description="Alternative action attempted if applicable")
    handover_id: str | None = Field(default=None, description="Handover ID if branch was HANDOVER_TO_USER")


class ResolutionDecisionResponse(BaseModel):
    """Recorded resolution decision descriptor."""

    session_id: str = Field(..., description="Session identifier")
    diagnostic_id: str = Field(..., description="Addressed diagnostic identifier")
    chosen_branch: ResolutionBranchEnum = Field(..., description="Final resolution branch")
    decision_rationale: str = Field(..., description="Rationale")
    timestamp: float = Field(..., description="Epoch timestamp")
    alternative_attempted: str | None = Field(default=None, description="Alternative attempted")
    handover_id: str | None = Field(default=None, description="Handover identifier")


class AutoReviewResolutionMetricsResponse(BaseModel):
    """Cumulative operational metrics for auto-review denial resolution."""

    total_denials_processed: int = Field(..., ge=0)
    branch_ask_user_count: int = Field(..., ge=0)
    branch_alternative_count: int = Field(..., ge=0)
    branch_handover_count: int = Field(..., ge=0)
    branch_stop_count: int = Field(..., ge=0)
    handovers_executed_by_user: int = Field(..., ge=0)
    handovers_dismissed_by_user: int = Field(..., ge=0)
