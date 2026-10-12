"""Pydantic schemas for Untrusted Webhook Prompt Injection Defense and Toolset Demotion.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for origin taint tracking, dynamic toolset masking,
  tool execution gating, and human admin approval cards.

[POS]
- Server schemas. Exposes typed contracts for webhook event ingress,
  automated tool demotion, and interactive escalation cards.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class OriginTaintDto(BaseModel):
    """Specification of external origin taint for an incoming event or message."""

    model_config = ConfigDict(extra="forbid")

    is_untrusted_external_content: bool = Field(
        ..., description="Whether the payload content originates from an untrusted public source"
    )
    origin_source: str = Field(
        ..., description="Ingress channel (e.g. github_pr, gitlab_issue, public_webhook)"
    )
    sender_identity: str = Field(
        ..., description="Identity or username of external payload author"
    )
    received_at: float = Field(default_factory=time.time, description="Unix timestamp of event reception")


class FilterToolsetRequest(BaseModel):
    """Payload to request dynamic tool masking based on origin taint."""

    model_config = ConfigDict(extra="forbid")

    all_tools: list[str] = Field(..., description="Full list of candidate tools available to the Agent")
    taint: OriginTaintDto | None = Field(default=None, description="Optional origin taint metadata")


class FilterToolsetResponse(BaseModel):
    """Result of dynamic toolset demotion."""

    model_config = ConfigDict(extra="forbid")

    allowed_tools: list[str] = Field(..., description="Safe tools permitted for execution")
    demoted_tools: list[str] = Field(default_factory=list, description="High-risk tools stripped out")
    is_tainted: bool = Field(..., description="Whether the session is currently marked as tainted")


class EvaluateExecutionRequest(BaseModel):
    """Request to evaluate whether a tool invocation is allowed or requires admin approval."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Task or session identifier")
    tool_name: str = Field(..., description="Name of the tool the Agent is attempting to invoke")
    tool_arguments: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict, description="Parameters passed to the tool invocation"
    )
    taint: OriginTaintDto | None = Field(default=None, description="Origin taint metadata")


class AdminApprovalCardDto(BaseModel):
    """Interactive card representation for human approval escalation."""

    model_config = ConfigDict(extra="forbid")

    card_id: str = Field(..., description="Unique approval card identifier")
    task_id: str = Field(..., description="Task identifier")
    origin_source: str = Field(..., description="Untrusted origin channel")
    requested_tool: str = Field(..., description="High-risk tool requiring approval")
    tool_arguments: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict, description="Arguments proposed for the tool"
    )
    risk_reason: str = Field(..., description="Security rationale for blocking auto-execution")
    status: str = Field(..., description="Status: pending, approved, rejected, expired")
    created_at: float = Field(..., description="Timestamp of card creation")
    expires_at: float = Field(..., description="Timestamp when card expires")


class EvaluateExecutionResponse(BaseModel):
    """Verdict of tool execution evaluation."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool = Field(..., description="Whether execution may proceed immediately")
    requires_approval: bool = Field(..., description="Whether execution was escalated to an admin card")
    card: AdminApprovalCardDto | None = Field(default=None, description="Generated approval card if escalated")
    message: str = Field(..., description="Status message or denial reason")
