"""Pydantic V2 schemas for Coding Agent Wave Preset Pipeline (Item 45).

[INPUT]
- CreateWaveSessionRequest, UpdateWaveTaskRequest.

[OUTPUT]
- WaveTaskNodeDTO, WavePresetConfigDTO, WaveExecutionProgressDTO.

[POS]
- Server-side typed DTO schemas for optional coding agent wave execution.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class WaveStageEnum(enum.StrEnum):
    """Discrete stages of the coding wave pipeline."""

    PLANNING = "planning"
    WAVE1_DEV = "wave1_dev"
    WAVE2_REVIEW = "wave2_review"
    WAVE3_TEST = "wave3_test"
    WAVE4_VISUAL = "wave4_visual"
    WAVE5_EVAL = "wave5_eval"


class WaveTaskStatusEnum(enum.StrEnum):
    """Execution status of an individual task node in the wave."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WaveTaskNodeDTO(BaseModel):
    """Data transfer object for a wave task node."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., min_length=1, description="Unique task identifier")
    stage: WaveStageEnum = Field(..., description="Target wave stage")
    title: str = Field(..., min_length=1, description="Human-readable task title")
    role: str = Field(..., min_length=1, description="Assigned developer/analyst role")
    model_override: str | None = Field(default=None, description="Model routing preference")
    status: WaveTaskStatusEnum = Field(
        default=WaveTaskStatusEnum.PENDING, description="Current task state"
    )
    output_summary: str | None = Field(
        default=None, description="Optional brief output summary or evidence"
    )


class WavePresetConfigDTO(BaseModel):
    """Preset configuration specification for the full-stack development wave pipeline."""

    model_config = ConfigDict(frozen=True)

    preset_id: str = Field(
        default="full-stack-dev-wave", description="Preset identifier"
    )
    name: str = Field(
        default="Full-Stack Development Wave Pipeline", description="Human-readable preset name"
    )
    description: str = Field(..., description="Pipeline architecture description")
    role_model_routing: dict[str, str] = Field(
        default_factory=lambda: {
            "tech-lead": "kimi-k3",
            "backend-dev": "ornith-1.5",
            "frontend-dev": "kimi-k3",
            "code-reviewer": "glm-5.3",
            "qa-tester": "ornith-1.5",
            "acceptance-eval": "kimi-k3",
        },
        description="Role-to-model routing table",
    )


class WaveExecutionProgressDTO(BaseModel):
    """Progress snapshot of an active wave session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Associated chat session ID")
    current_stage: WaveStageEnum = Field(..., description="Active pipeline stage")
    tasks: list[WaveTaskNodeDTO] = Field(
        default_factory=list, description="Ordered list of task nodes in pipeline"
    )
    is_completed: bool = Field(default=False, description="Whether entire pipeline is done")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Snapshot timestamp"
    )


class CreateWaveSessionRequest(BaseModel):
    """Request to initialize a new coding wave pipeline for a chat session."""

    model_config = ConfigDict(frozen=True)

    preset: WavePresetConfigDTO | None = Field(
        default=None, description="Optional preset configuration override"
    )
    custom_tasks: list[WaveTaskNodeDTO] | None = Field(
        default=None, description="Optional custom task nodes list"
    )


class UpdateWaveTaskRequest(BaseModel):
    """Request to update execution status and output summary of a task node."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., min_length=1, description="Target task ID to update")
    status: WaveTaskStatusEnum = Field(..., description="New task status")
    output_summary: str | None = Field(
        default=None, description="Optional task output summary"
    )
