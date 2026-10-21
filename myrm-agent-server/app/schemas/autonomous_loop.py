"""Pydantic V2 schemas for Goal-Driven Autonomous Orchestration Loop (Item 38).

[INPUT]
- StartAutonomousLoopRequest, AdvanceStepRequest, SetModeRequest, CompleteLoopRequest.

[OUTPUT]
- Strongly-typed DTOs for autonomous orchestration mode toggling, step progression,
  watchdog inspection, and audit history.

[POS]
- Server-side typed contracts for autonomous versus supervised orchestration pacing.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class OrchestrationModeEnum(enum.StrEnum):
    """Operational mode of the multi-agent orchestrator loop."""

    AUTONOMOUS = "autonomous"
    SUPERVISED = "supervised"
    PAUSED = "paused"
    COMPLETED = "completed"


class StepStatusEnum(enum.StrEnum):
    """Execution status of an individual autonomous loop step."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PAUSED = "paused"


class AutonomousLoopConfigDTO(BaseModel):
    """Watchdog and pacing configuration for autonomous loops."""

    model_config = ConfigDict(frozen=True)

    max_autonomous_steps: int = Field(default=10, ge=1, le=100, description="Watchdog maximum steps")
    pause_on_approval: bool = Field(default=True, description="Pause on human approval required")
    pause_on_error: bool = Field(default=True, description="Pause on step execution failure")
    heartbeat_interval_s: float = Field(default=1.0, ge=0.1, le=60.0, description="Heartbeat interval in seconds")


class AutonomousLoopStepDTO(BaseModel):
    """Record of a single autonomously advanced action or heartbeat step."""

    model_config = ConfigDict(frozen=True)

    step_index: int = Field(..., ge=0, description="1-based step counter")
    action_type: str = Field(..., min_length=1, description="Category of step action")
    description: str = Field(..., description="Action narrative summary")
    status: StepStatusEnum = Field(default=StepStatusEnum.SUCCESS, description="Step outcome status")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC), description="Step timestamp")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Contextual tags")


class AutonomousLoopStateResponse(BaseModel):
    """Real-time consolidated state of an orchestrated autonomous loop."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Target chat/task session ID")
    goal_id: str = Field(..., description="Target goal or kanban task ID")
    mode: OrchestrationModeEnum = Field(..., description="Current operational loop mode")
    current_step: int = Field(..., ge=0, description="Steps executed so far")
    max_steps: int = Field(..., ge=1, description="Configured step ceiling")
    is_active: bool = Field(..., description="Whether loop is actively cruising")
    history: list[AutonomousLoopStepDTO] = Field(default_factory=list, description="Step progression audit trail")
    pause_reason: str = Field(default="", description="Reason for pause if not cruising")
    started_at: datetime = Field(..., description="Timestamp loop started")
    last_advanced_at: datetime = Field(..., description="Timestamp of last step advance")


class StartAutonomousLoopRequest(BaseModel):
    """Request payload to initiate an autonomous orchestration loop."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Chat or task session identifier")
    goal_id: str = Field(..., min_length=1, description="Goal identifier to pursue autonomously")
    mode: OrchestrationModeEnum = Field(
        default=OrchestrationModeEnum.AUTONOMOUS,
        description="Starting orchestration mode",
    )
    config: AutonomousLoopConfigDTO | None = Field(default=None, description="Optional custom watchdog pacing config")


class AdvanceStepRequest(BaseModel):
    """Request payload to advance the autonomous loop by one action step."""

    model_config = ConfigDict(frozen=True)

    action_type: str = Field(..., min_length=1, description="Action category (e.g. subagent_task, tool_call)")
    description: str = Field(..., min_length=1, description="Summary of action taken or planned")
    requires_approval: bool = Field(default=False, description="Whether action triggers HITL approval pause")
    is_error: bool = Field(default=False, description="Whether step encountered an execution error")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Metadata tags")


class SetModeRequest(BaseModel):
    """Request payload to switch loop operational mode."""

    model_config = ConfigDict(frozen=True)

    mode: OrchestrationModeEnum = Field(..., description="New operational mode")
    reason: str = Field(default="", description="Reason for mode change")


class CompleteLoopRequest(BaseModel):
    """Request payload to conclude an autonomous loop."""

    model_config = ConfigDict(frozen=True)

    summary: str = Field(default="", description="Final completion summary")
