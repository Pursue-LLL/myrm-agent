"""Pydantic V2 schemas for Native Subagent Lifecycle Toolchain (Item 46).

[INPUT]
- SubagentSpawnRequest, SubagentSendInputRequest, SubagentKillRequest, SubagentWaitRequest.

[OUTPUT]
- SubagentTaskItemDTO, SubagentWaitResponseDTO, SubagentListResponseDTO, SubagentInputMessageDTO.

[POS]
- Server-side typed DTO schemas for native subagent fine-grained lifecycle management.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class SubagentStatusEnum(enum.StrEnum):
    """Lifecycle status of a native subagent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    TIMEOUT = "timeout"


class SubagentInputMessageDTO(BaseModel):
    """DTO for an input message injected into an active subagent."""

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(..., description="Unique message identifier")
    subagent_id: str = Field(..., description="Target subagent identifier")
    content: str = Field(..., min_length=1, description="Message content")
    sender_role: str = Field(default="orchestrator", description="Sender role")
    created_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp of injection",
    )


class SubagentEventItemDTO(BaseModel):
    """DTO for an audit event during subagent lifecycle."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Lifecycle event type")
    subagent_id: str = Field(..., description="Target subagent identifier")
    payload: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Structured event payload"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Event emission timestamp",
    )


class SubagentTaskItemDTO(BaseModel):
    """DTO representing the full state of a native subagent task."""

    model_config = ConfigDict(frozen=True)

    subagent_id: str = Field(..., description="Unique subagent identifier")
    parent_session_id: str = Field(..., description="Parent chat session identifier")
    task_prompt: str = Field(..., description="Task prompt assigned to subagent")
    agent_profile: str = Field(..., description="Subagent role/profile name")
    tools_whitelist: list[str] = Field(default_factory=list, description="Whitelisted tool names")
    status: SubagentStatusEnum = Field(..., description="Current lifecycle status")
    timeout_seconds: float = Field(default=60.0, description="Execution timeout budget in seconds")
    created_at: str = Field(..., description="Task creation timestamp")
    started_at: str | None = Field(default=None, description="Task start timestamp")
    ended_at: str | None = Field(default=None, description="Task completion/termination timestamp")
    result_summary: str | None = Field(default=None, description="Output summary if completed")
    error_detail: str | None = Field(default=None, description="Error reason if failed or timeout")
    kill_reason: str | None = Field(default=None, description="Reason if killed manually")
    token_usage: int = Field(default=0, description="Tokens consumed")
    step_count: int = Field(default=0, description="Tool execution steps taken")
    input_queue: list[SubagentInputMessageDTO] = Field(
        default_factory=list, description="Injected input messages"
    )
    events: list[SubagentEventItemDTO] = Field(
        default_factory=list, description="Audit events trail"
    )


class SubagentSpawnRequest(BaseModel):
    """Request payload to spawn an isolated subagent."""

    task_prompt: str = Field(..., min_length=1, description="Task instruction for subagent")
    agent_profile: str = Field(default="general_worker", description="Subagent profile archetype")
    tools_whitelist: list[str] = Field(
        default_factory=list, description="Permitted tool names"
    )
    timeout_seconds: float = Field(
        default=60.0, gt=0.0, le=600.0, description="Timeout budget in seconds"
    )


class SubagentSendInputRequest(BaseModel):
    """Request payload to inject message into a running subagent."""

    content: str = Field(..., min_length=1, description="Guidance or input message")
    sender_role: str = Field(default="orchestrator", description="Sender role identifier")


class SubagentKillRequest(BaseModel):
    """Request payload to kill a running subagent."""

    reason: str = Field(default="manual_kill", description="Reason for termination")


class SubagentWaitRequest(BaseModel):
    """Request payload to wait for multiple subagents."""

    subagent_ids: list[str] = Field(..., min_length=1, description="List of subagent IDs to wait for")
    timeout_seconds: float = Field(
        default=30.0, gt=0.0, le=300.0, description="Maximum wait time in seconds"
    )


class SubagentWaitResponseDTO(BaseModel):
    """Response payload for subagent wait operation."""

    model_config = ConfigDict(frozen=True)

    all_completed: bool = Field(..., description="True if all subagents reached terminal state")
    completed_count: int = Field(..., description="Number of completed tasks")
    failed_count: int = Field(..., description="Number of failed tasks")
    killed_count: int = Field(..., description="Number of killed tasks")
    timeout_count: int = Field(..., description="Number of timed out tasks")
    tasks: list[SubagentTaskItemDTO] = Field(..., description="Status snapshot of waited tasks")


class SubagentListResponseDTO(BaseModel):
    """Response payload for querying subagent list."""

    model_config = ConfigDict(frozen=True)

    tasks: list[SubagentTaskItemDTO] = Field(..., description="Matching subagents")
    total: int = Field(..., description="Total count")
