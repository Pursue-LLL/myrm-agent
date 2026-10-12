"""Pydantic schemas for HITL Denial Events and Synthetic Tool Result Generation.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for processing manual tool rejections and generating synthetic results.

[POS]
- Server schemas for AgentScope-Java #2546 HITL denial handling.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DenialResolutionPolicyDto(StrEnum):
    """Action policy when all tool calls in a reasoning step are denied."""

    STOP = "stop"
    CONTINUE = "continue"


class ToolDenialItemDto(BaseModel):
    """Specification of a denied tool call."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(
        ..., description="Unique ID of the tool call rejected by user"
    )
    tool_name: str = Field(..., description="Name of the tool rejected")
    reason: str = Field(
        default="Operation rejected by user",
        description="Rejection reason or policy note",
    )
    custom_feedback: str | None = Field(
        default=None, description="Optional custom instruction from user"
    )


class SyntheticToolResultBlockDto(BaseModel):
    """Synthetic ToolResult block created to answer denied tool calls for LLM context."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    tool_name: str
    output: str
    is_error: bool = True
    metadata: dict[str, str] = Field(default_factory=dict)


class ProcessDenialsRequest(BaseModel):
    """Request payload for processing tool denials."""

    model_config = ConfigDict(extra="forbid")

    denied_items: list[ToolDenialItemDto] = Field(
        ..., description="List of tool calls explicitly denied by user"
    )
    total_tool_calls_in_step: int = Field(
        ..., description="Total tool calls initiated in this reasoning cycle"
    )
    override_policy: DenialResolutionPolicyDto | None = Field(
        default=None, description="Optional override policy for all-denied outcome"
    )


class ProcessDenialsResponse(BaseModel):
    """Response payload containing synthetic tool results and stop/continue decision."""

    model_config = ConfigDict(extra="forbid")

    all_tools_denied: bool = Field(
        ..., description="Whether every tool call in this step was rejected"
    )
    total_requested: int = Field(..., description="Total tool calls in reasoning step")
    total_denied: int = Field(..., description="Total tool calls rejected")
    resolution_action: DenialResolutionPolicyDto = Field(
        ..., description="Selected policy: stop or continue"
    )
    synthetic_results: list[SyntheticToolResultBlockDto] = Field(
        ..., description="Generated synthetic ToolResult blocks"
    )
    stop_requested: bool = Field(
        ..., description="Whether agent execution should be halted"
    )
