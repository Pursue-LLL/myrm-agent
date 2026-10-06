"""Pydantic schemas for Externally Visible Irreversible Action Static Classification Gate.

[INPUT]
- None (Self-contained schema representations for externally visible actions)

[OUTPUT]
- EvaluateActionRequest, ExternalActionClassificationResponse, BatchEvaluateActionsRequest, BatchEvaluateActionsResponse

[POS]
- app.schemas.externally_visible_action
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateActionRequest(BaseModel):
    """Request payload for evaluating tool external visibility."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., min_length=1, max_length=128, description="Tool name to evaluate")
    custom_is_third_party_visible: bool | None = Field(
        default=None,
        description="Optional explicit third-party visibility override flag",
    )


class ExternalActionClassificationResponse(BaseModel):
    """Evaluation result detailing whether an action escapes local boundary."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Evaluated tool identifier")
    is_third_party_visible: bool = Field(..., description="Whether action is visible to external third parties")
    requires_mandatory_human_review: bool = Field(
        ...,
        description="Whether mandatory human confirmation is required",
    )
    hide_allow_always: bool = Field(
        ...,
        description="Whether persistent allow-always option is suppressed",
    )
    visibility_scope: str = Field(..., description="Scope: INTERNAL_ONLY, USER_LOCAL, or THIRD_PARTY_VISIBLE")
    rationale: str = Field(..., description="Explanation for the classification")


class RecordExternalActionAuditRequest(BaseModel):
    """Payload to log an externally visible action attempt and review outcome."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(..., min_length=1, max_length=64, description="Unique action event ID")
    session_id: str = Field(..., min_length=1, max_length=64, description="Session ID")
    agent_id: str = Field(..., min_length=1, max_length=64, description="Agent ID")
    tool_name: str = Field(..., min_length=1, max_length=128, description="Tool name executed or requested")
    recipient_or_destination: str = Field(
        ...,
        min_length=1,
        max_length=256,
        description="Target recipient, email, channel, or webhook URL",
    )
    content_preview: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Preview of the outbound payload or message",
    )
    is_approved: bool = Field(..., description="Whether the action was approved by human operator")
    approved_by: str | None = Field(
        default=None,
        max_length=64,
        description="Identifier of reviewing operator or reviewer",
    )


class AuditedExternalActionResponse(BaseModel):
    """Audit record detail for an outbound action."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    session_id: str
    agent_id: str
    tool_name: str
    recipient_or_destination: str
    content_preview: str
    is_approved: bool
    approved_by: str | None
    timestamp: float


class AuditTrailResponse(BaseModel):
    """List of logged external action audit records."""

    model_config = ConfigDict(extra="forbid")

    records: list[AuditedExternalActionResponse]
    total: int
