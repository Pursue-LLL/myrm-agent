"""Pydantic V2 schemas for Clean-Code Assembly Pipeline and Architecture Dependency Linter (Item 62).

[INPUT]
- CreateCleanCodeTaskRequest, AdvanceStageRequest, LinterCheckRequest.

[OUTPUT]
- CleanCodeTaskDTO, StageArtifactDTO, ArchitectureViolationDTO, LinterResultDTO.

[POS]
- Server-side DTO layer for Item 62 Clean-Code assembly pipeline.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class PipelineStageDTOEnum(enum.StrEnum):
    """Five-stage Clean-Code assembly pipeline stages."""

    SPECIFIER = "specifier"
    CODER = "coder"
    CLEANER = "cleaner"
    HARDENER = "hardener"
    QA = "qa"


class StageStatusDTOEnum(enum.StrEnum):
    """Lifecycle status of a stage or overall task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ViolationTypeDTOEnum(enum.StrEnum):
    """Architecture dependency violation categories."""

    INVERTED_DEPENDENCY = "inverted_dependency"
    LAYER_BYPASS = "layer_bypass"
    CIRCULAR_DEPENDENCY = "circular_dependency"


class ArchitectureViolationDTO(BaseModel):
    """Details of a single architectural rule violation."""

    model_config = ConfigDict(frozen=True)

    source_module: str = Field(..., description="Module initiating the invalid dependency")
    target_module: str = Field(..., description="Forbidden target module being imported")
    violation_type: ViolationTypeDTOEnum = Field(..., description="Type of violation")
    rule_description: str = Field(..., description="Human-readable explanation of why this import is forbidden")
    remediation_suggestion: str = Field(default="", description="Refactoring recommendation (e.g. DIP interface extraction)")


class DependencyRuleDTO(BaseModel):
    """Custom architecture dependency rule definition."""

    model_config = ConfigDict(frozen=True)

    source_layer: str = Field(..., min_length=1, description="Layer name of source module")
    allowed_target_layers: list[str] = Field(default_factory=list, description="Allowed target layer names")


class LinterResultDTO(BaseModel):
    """Summary result of architecture AST static analysis."""

    model_config = ConfigDict(frozen=True)

    is_valid: bool = Field(..., description="True if 0 architecture violations were found")
    violations: list[ArchitectureViolationDTO] = Field(default_factory=list)
    scanned_files_count: int = Field(default=0, ge=0)
    dependency_edges: list[list[str]] = Field(default_factory=list)


class StageArtifactDTO(BaseModel):
    """Immutable deliverable handed over across pipeline stages."""

    model_config = ConfigDict(frozen=True)

    stage: PipelineStageDTOEnum = Field(...)
    title: str = Field(...)
    content: str = Field(default="")
    metadata: dict[str, str] = Field(default_factory=dict)


class CleanCodeTaskDTO(BaseModel):
    """Overall state of a Clean-Code assembly task."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(..., min_length=1)
    session_id: str = Field(default="default", min_length=1)
    title: str = Field(..., min_length=1)
    spec_prompt: str = Field(default="")
    current_stage: PipelineStageDTOEnum = Field(...)
    status: StageStatusDTOEnum = Field(...)
    artifacts: dict[str, StageArtifactDTO] = Field(default_factory=dict)
    stage_history: list[str] = Field(default_factory=list)
    created_at: float = Field(default=0.0)
    updated_at: float = Field(default=0.0)


class CreateCleanCodeTaskRequest(BaseModel):
    """Request payload to initiate a Clean-Code assembly pipeline."""

    model_config = ConfigDict(frozen=True)

    task_id: str | None = Field(default=None, description="Optional custom task ID")
    session_id: str = Field(default="default", min_length=1, description="Multi-agent session ID")
    title: str = Field(..., min_length=1, description="Feature or task title")
    spec_prompt: str = Field(..., min_length=1, description="Specification requirements handed to Specifier")
    custom_rules: list[DependencyRuleDTO] | None = Field(default=None)


class AdvanceStageRequest(BaseModel):
    """Request payload to advance the pipeline to the next stage."""

    model_config = ConfigDict(frozen=True)

    artifact_title: str = Field(..., min_length=1, description="Title of stage deliverable")
    artifact_content: str = Field(default="", description="Deliverable or design summary")
    metadata: dict[str, str] | None = Field(default=None, description="Optional stage metadata")
    source_code_map: dict[str, str] | None = Field(
        default=None,
        description="Optional file-to-content map to run architecture linter gates against before advance",
    )


class LinterCheckRequest(BaseModel):
    """Ad-hoc static architecture check on a codebase in-memory snapshot."""

    model_config = ConfigDict(frozen=True)

    source_code_map: dict[str, str] = Field(..., description="Mapping of relative file path to source code")
    custom_rules: list[DependencyRuleDTO] | None = Field(default=None)
