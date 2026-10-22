"""Pydantic V2 schemas for Planner-Generator-Evaluator Tri-Role Separation Pipeline (Item 40).

[INPUT]
- CreateTriRoleSessionRequest, PlanSubmissionRequest, GenerationSubmissionRequest,
  EvaluateStageRequest, RestoreFromManifestRequest.

[OUTPUT]
- Strongly-typed DTOs for cognitive separation stages, independent evaluator verdicts,
  and cross-session artifact handoff manifests.

[POS]
- Server-side typed schemas for tri-role pipeline APIs.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class TriRoleTypeEnum(enum.StrEnum):
    """Cognitively separated multi-agent roles preventing self-delusion."""

    PLANNER = "planner"
    GENERATOR = "generator"
    EVALUATOR = "evaluator"


class StageStatusEnum(enum.StrEnum):
    """Discrete lifecycle progress status for a pipeline stage."""

    PLANNED = "planned"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AcceptanceCriterionDTO(BaseModel):
    """Deterministic acceptance assertion formulated by the Planner."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str = Field(..., min_length=1, description="Unique criterion identifier")
    description: str = Field(..., min_length=1, description="Acceptance description")
    assertion_rule: str = Field(..., min_length=1, description="Verification condition or rule")
    is_satisfied: bool = Field(default=False, description="Verification satisfaction result")


class EvaluationVerdictDTO(BaseModel):
    """Independent adversary verdict rendered by the Scalable Evaluator."""

    model_config = ConfigDict(frozen=True)

    is_accepted: bool = Field(..., description="Whether stage passed evaluation")
    score: float = Field(..., ge=0.0, le=1.0, description="Acceptance score ratio")
    evaluator_notes: str = Field(..., description="Objective assessment narrative")
    criteria_results: dict[str, bool] = Field(
        default_factory=dict, description="Criterion ID to verification boolean map"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Evaluation timestamp"
    )


class ArtifactManifestDTO(BaseModel):
    """Standardized cross-session artifact package enabling zero-loss handoff."""

    model_config = ConfigDict(frozen=True)

    manifest_id: str = Field(..., min_length=1, description="Unique manifest ID")
    session_id: str = Field(..., min_length=1, description="Origin session identifier")
    stage_index: int = Field(..., ge=0, description="Stage index of artifact completion")
    produced_files: list[str] = Field(default_factory=list, description="Deliverable file paths")
    passed_assertions: list[str] = Field(
        default_factory=list, description="Verified assertion descriptions"
    )
    key_constraints: list[str] = Field(
        default_factory=list, description="Non-negotiable constraints preserved"
    )
    pending_todos: list[str] = Field(
        default_factory=list, description="Subsequent tasks remaining"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )


class TriRolePipelineStageDTO(BaseModel):
    """Discrete horizon step governed by tri-role checks and balances."""

    model_config = ConfigDict(frozen=True)

    stage_id: str = Field(..., min_length=1, description="Unique stage ID")
    stage_name: str = Field(..., min_length=1, description="Stage name or milestone")
    status: StageStatusEnum = Field(default=StageStatusEnum.PLANNED, description="Stage status")
    planner_output: str = Field(default="", description="Planner plan and breakdown")
    criteria: list[AcceptanceCriterionDTO] = Field(
        default_factory=list, description="Acceptance criteria"
    )
    generator_output: str = Field(default="", description="Generator implementation summary")
    produced_files: list[str] = Field(
        default_factory=list, description="Output deliverable files"
    )
    evaluation: EvaluationVerdictDTO | None = Field(
        default=None, description="Evaluator verdict"
    )
    manifest: ArtifactManifestDTO | None = Field(
        default=None, description="Generated handoff manifest if accepted"
    )


class TriRoleSessionResponse(BaseModel):
    """Consolidated state representation of a tri-role orchestration session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Session ID")
    task_description: str = Field(..., description="High-level goal or task")
    stages: list[TriRolePipelineStageDTO] = Field(
        default_factory=list, description="Discrete stages list"
    )
    current_stage_index: int = Field(default=0, ge=0, description="Active stage index")
    is_completed: bool = Field(default=False, description="Whether all stages completed")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Last update timestamp"
    )


class CreateTriRoleSessionRequest(BaseModel):
    """Request to initialize a new tri-role separation pipeline session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Unique session ID")
    task_description: str = Field(..., min_length=1, description="Target task description")
    stage_names: list[str] = Field(
        ..., min_length=1, description="Discrete stage milestone names"
    )


class PlanSubmissionRequest(BaseModel):
    """Request by Planner to formulate stage plan and acceptance criteria."""

    model_config = ConfigDict(frozen=True)

    planner_output: str = Field(..., min_length=1, description="Plan details and instructions")
    criteria: list[AcceptanceCriterionDTO] = Field(
        ..., min_length=1, description="Deterministic criteria assertions"
    )


class GenerationSubmissionRequest(BaseModel):
    """Request by Generator to submit execution deliverables."""

    model_config = ConfigDict(frozen=True)

    generator_output: str = Field(..., min_length=1, description="Implementation summary")
    produced_files: list[str] = Field(
        default_factory=list, description="Generated file paths"
    )


class EvaluateStageRequest(BaseModel):
    """Request by independent Evaluator to record verification verdict."""

    model_config = ConfigDict(frozen=True)

    evaluator_notes: str = Field(..., min_length=1, description="Evaluator feedback notes")
    criteria_evaluations: dict[str, bool] = Field(
        default_factory=dict, description="Criterion satisfaction results"
    )
    min_pass_rate: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Required pass threshold"
    )


class RestoreFromManifestRequest(BaseModel):
    """Request to restore and continue execution in a new session from an artifact manifest."""

    model_config = ConfigDict(frozen=True)

    new_session_id: str = Field(..., min_length=1, description="Target new session ID")
    task_description: str = Field(..., min_length=1, description="Continuation task description")
    manifest: ArtifactManifestDTO = Field(..., description="Prior session artifact manifest")
    subsequent_stage_names: list[str] = Field(
        ..., min_length=1, description="Names of stages to execute after restore"
    )
