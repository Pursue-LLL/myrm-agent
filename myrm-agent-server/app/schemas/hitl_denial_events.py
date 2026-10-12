"""Pydantic schemas for HITL denial events and process outcomes.

[INPUT]
- Web API payloads submitting user confirmation/denial decisions.

[OUTPUT]
- Serialized tool result events and all-tools-denied aggregate event responses.

[POS]
- Server-side DTO contracts for Human-in-the-Loop decision processing.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ToolUseBlockDto(BaseModel):
    """Data transfer object for a pending tool call."""

    id: str = Field(description="Unique tool call identifier")
    name: str = Field(description="Tool name")
    arguments: dict[str, str | int | float | bool | list[str] | dict[str, str]] = (
        Field(default_factory=dict, description="Tool invocation parameters")
    )


class ConfirmResultDto(BaseModel):
    """User decision for a tool call."""

    tool_call_id: str = Field(description="Target tool call identifier")
    tool_name: str = Field(description="Target tool name")
    confirmed: bool = Field(description="True if approved, False if denied")
    reason: str | None = Field(
        default=None, description="Optional custom denial reason from user"
    )


class ToolResultEventDto(BaseModel):
    """Emitted tool result event representation."""

    event_id: str = Field(description="Unique event identifier")
    tool_call_id: str = Field(description="Target tool call identifier")
    tool_name: str = Field(description="Target tool name")
    state: Literal["ALLOWED", "DENIED", "ERROR"] = Field(
        description="Execution state"
    )
    output_text: str = Field(description="Tool result output or denial reason")
    created_at: str = Field(description="ISO timestamp of event emission")


class AllToolsDeniedEventDto(BaseModel):
    """Event emitted when all tool calls in a step are denied."""

    event_id: str = Field(description="Unique aggregate event identifier")
    session_id: str = Field(description="Target session identifier")
    step_id: str = Field(description="Target step identifier")
    policy_applied: Literal["HALT", "RESUME_WITH_FEEDBACK"] = Field(
        description="Policy applied"
    )
    should_stop: bool = Field(
        description="Whether agent loop is commanded to halt"
    )
    stop_reason: str | None = Field(
        default=None, description="Terminal stop reason"
    )
    denied_tool_count: int = Field(description="Number of denied tool calls")
    created_at: str = Field(description="ISO timestamp of aggregate event")


class ProcessHitlDecisionsRequest(BaseModel):
    """Request payload for processing a batch of HITL decisions."""

    session_id: str = Field(description="Session identifier")
    step_id: str = Field(description="Reasoning step identifier")
    tool_calls: list[ToolUseBlockDto] = Field(
        description="Proposed tool calls awaiting approval"
    )
    decisions: list[ConfirmResultDto] = Field(
        description="Decisions made by reviewer"
    )
    policy: Literal["HALT", "RESUME_WITH_FEEDBACK"] | None = Field(
        default=None, description="Optional override policy for full denials"
    )


class ProcessHitlDecisionsResponse(BaseModel):
    """Response containing processed events and loop control flags."""

    session_id: str = Field(description="Session identifier")
    step_id: str = Field(description="Reasoning step identifier")
    total_calls: int = Field(description="Total tool calls evaluated")
    confirmed_count: int = Field(description="Count of confirmed calls")
    denied_count: int = Field(description="Count of denied calls")
    all_denied: bool = Field(description="True if all calls were denied")
    tool_result_events: list[ToolResultEventDto] = Field(
        description="Explicit tool result events"
    )
    all_tools_denied_event: AllToolsDeniedEventDto | None = Field(
        default=None, description="Full denial aggregate event if triggered"
    )
    can_resume: bool = Field(description="Whether the agent is allowed to resume")
    terminal_reason: str | None = Field(
        default=None, description="Terminal reason if halted"
    )


class HitlPoliciesConfigResponse(BaseModel):
    """Configuration metadata of HITL denial policies."""

    available_policies: list[str] = Field(
        description="Supported all-tools-denied policies"
    )
    default_policy: str = Field(description="Current system default policy")
    strict_halt_tools: list[str] = Field(
        description="Tools strictly requiring halt on denial"
    )
