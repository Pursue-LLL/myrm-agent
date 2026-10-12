"""Pydantic DTO schemas for HITL Approval Fail-Closed Safety Gate & Invariant Secondary Guard.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for HITL execution gating evaluation and secondary invariant validation.

[POS]
- Server schemas. Exposes typed contracts for human-in-the-loop fail-closed control.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class HitlEvaluateExecutionRequest(BaseModel):
    """Request payload to evaluate tool execution through HITL fail-closed gating."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Target tool identifier to evaluate")
    arguments: dict[str, str] = Field(
        default_factory=dict, description="Key-value arguments map for the tool execution"
    )
    user_approval: bool | None = Field(
        default=None,
        description="Explicit human decision: True=Approve, False=Reject, None=Unavailable/no callback",
    )
    simulate_timeout: bool = Field(
        default=False, description="Simulate human approval communication timeout"
    )
    channel_connected: bool = Field(
        default=True, description="Whether approval channel (WebSocket/Relay) is active"
    )
    is_service_available: bool = Field(
        default=True, description="Whether human approval service component is reachable"
    )


class HitlExecutionVerdictDto(BaseModel):
    """Evaluation verdict for HITL tool execution request."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Evaluated tool name")
    arguments: dict[str, str] = Field(..., description="Tool arguments map")
    approval_decision: str = Field(
        ..., description="APPROVED, REJECTED_USER, or REJECTED_FAIL_CLOSED"
    )
    fail_closed_reason: str = Field(
        ..., description="NONE, TIMEOUT, CHANNEL_DISCONNECTED, SERVICE_UNAVAILABLE, or TRANSPORT_ERROR"
    )
    guard_verdict: str = Field(
        ..., description="PASSED, BLOCKED_PHYSICAL_INVARIANT, or BLOCKED_HIGH_RISK_PATTERN"
    )
    is_execution_permitted: bool = Field(
        ..., description="Whether tool execution is strictly permitted"
    )
    audit_id: str = Field(..., description="Unique immutable audit trace ID")
    audit_rationale: str = Field(..., description="Reasoning and decision trail")


class SecondaryGuardCheckRequest(BaseModel):
    """Request payload to check invariant secondary guard constraints directly."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Tool name to inspect")
    arguments: dict[str, str] = Field(
        default_factory=dict, description="Tool execution arguments to validate"
    )


class SecondaryGuardCheckDto(BaseModel):
    """Direct secondary invariant guard evaluation outcome."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Target tool name")
    guard_verdict: str = Field(
        ..., description="PASSED, BLOCKED_PHYSICAL_INVARIANT, or BLOCKED_HIGH_RISK_PATTERN"
    )
    rationale: str = Field(..., description="Guard verdict rationale")
    is_permitted: bool = Field(
        ..., description="Whether invariant guard permits execution"
    )
