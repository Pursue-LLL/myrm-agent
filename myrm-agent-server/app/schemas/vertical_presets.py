"""Pydantic V2 schemas for Five Vertical Role Persona Presets and Sub-Bot Sandbox Tester (Item 64).

[INPUT]
- SubBotTestRequestDTO, RegisterPresetRequest, RecordAgentStepRequest.

[OUTPUT]
- VerticalRolePresetDTO, SubBotTestResultDTO, AgentFlowStepDTO, AgentFlowTraceDTO.

[POS]
- Server-side DTO layer for Item 64 vertical role presets, sandbox test runs, and agent-to-agent telemetry.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class VerticalRoleCategoryDTOEnum(enum.StrEnum):
    """Five core vertical agent persona categories."""

    LIFE_ADMIN = "life_admin"
    OFFICE_MANAGER = "office_manager"
    CLIPPER = "clipper"
    CHIEF_OF_STAFF = "chief_of_staff"
    SALES_TEAM = "sales_team"


class ReasoningEffortDTOEnum(enum.StrEnum):
    """Reasoning effort tier for specialist agents."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerticalRolePresetDTO(BaseModel):
    """DTO representing an out-of-the-box vertical persona preset."""

    model_config = ConfigDict(frozen=True)

    role_id: str = Field(..., min_length=1)
    category: VerticalRoleCategoryDTOEnum = Field(...)
    display_name: str = Field(..., min_length=1)
    description: str = Field(default="")
    persona_prompt: str = Field(default="")
    recommended_skills: list[str] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    reasoning_effort: ReasoningEffortDTOEnum = Field(default=ReasoningEffortDTOEnum.MEDIUM)
    typical_tasks: list[str] = Field(default_factory=list)


class RegisterPresetRequest(BaseModel):
    """Payload to register or update a custom vertical persona preset."""

    model_config = ConfigDict(frozen=True)

    role_id: str = Field(..., min_length=1)
    category: VerticalRoleCategoryDTOEnum = Field(...)
    display_name: str = Field(..., min_length=1)
    description: str = Field(default="")
    persona_prompt: str = Field(default="")
    recommended_skills: list[str] = Field(default_factory=list)
    recommended_tools: list[str] = Field(default_factory=list)
    reasoning_effort: ReasoningEffortDTOEnum = Field(default=ReasoningEffortDTOEnum.MEDIUM)
    typical_tasks: list[str] = Field(default_factory=list)


class SubBotTestRequestDTO(BaseModel):
    """Payload to initiate an isolated unit test for a specialist bot."""

    model_config = ConfigDict(frozen=True)

    role_id: str = Field(..., min_length=1)
    test_prompt: str = Field(..., min_length=1)
    mock_inputs: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)


class SubBotTestResultDTO(BaseModel):
    """DTO returning telemetry and assertion results from an isolated sandbox run."""

    model_config = ConfigDict(frozen=True)

    test_id: str = Field(...)
    role_id: str = Field(...)
    success: bool = Field(...)
    output_text: str = Field(default="")
    tool_calls_made: list[str] = Field(default_factory=list)
    execution_time_ms: float = Field(default=0.0)
    logs: list[str] = Field(default_factory=list)
    error_message: str | None = Field(default=None)


class AgentFlowStepDTO(BaseModel):
    """DTO representing an Agent-to-Agent interaction step."""

    model_config = ConfigDict(frozen=True)

    step_id: str = Field(..., min_length=1)
    source_agent_id: str = Field(..., min_length=1)
    target_agent_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    payload_summary: str = Field(default="")
    result_summary: str = Field(default="")
    duration_ms: float = Field(default=0.0)
    timestamp: float = Field(default=0.0)


class AgentFlowTraceDTO(BaseModel):
    """DTO representing the aggregated communication trace for an agent team session."""

    model_config = ConfigDict(frozen=True)

    trace_id: str = Field(...)
    session_id: str = Field(...)
    root_agent_id: str = Field(...)
    steps: list[AgentFlowStepDTO] = Field(default_factory=list)
    total_duration_ms: float = Field(default=0.0)
    is_loop_detected: bool = Field(default=False)


class RecordAgentStepRequest(BaseModel):
    """Payload to record a new agent-to-agent interaction step."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    root_agent_id: str = Field(..., min_length=1)
    step: AgentFlowStepDTO = Field(...)
