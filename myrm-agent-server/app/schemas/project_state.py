"""
[POS] app/schemas/project_state.py
[INPUT] pydantic
[OUTPUT] LivingFactDTO, CreateLivingFactRequestDTO, LivingFactListResponseDTO, ContextProjectionRequestDTO, ContextProjectionResponseDTO, ValidationAuditRequestDTO, ValidationAuditResponseDTO

Pydantic DTOs for ProjectState living fact ledger and four-tier context projection suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LivingFactDTO(BaseModel):
    """Data transfer object representing a living fact, decision, or constraint item."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Unique fact identifier")
    project_id: str = Field(..., description="Target project identifier")
    fact_type: str = Field(
        ...,
        description="Fact type: decision, rejected_alternative, constraint, interface_contract, validation_result",
    )
    title: str = Field(..., description="Short summary title of the fact or decision")
    content: str = Field(..., description="Detailed content of the fact or decision")
    target_components: list[str] = Field(
        default_factory=list, description="Target modules, components, or file paths"
    )
    reason_or_constraint: str = Field(
        default="", description="Underlying rationale, constraint rule, or rejection reason"
    )
    validation_count: int = Field(default=0, ge=0, description="Cumulative verified count")
    regression_count: int = Field(default=0, ge=0, description="Cumulative regression count")
    promotion_stage: str = Field(
        default="confirmed_fact",
        description="Promotion stage: observation, project_event, confirmed_fact, knowledge, skill",
    )
    created_at: str = Field(default="", description="ISO 8601 creation timestamp")
    updated_at: str = Field(default="", description="ISO 8601 last update timestamp")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Key-value strictly string typed metadata"
    )


class CreateLivingFactRequestDTO(BaseModel):
    """Payload to record or register a new living fact in the project state ledger."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Unique identifier for the new fact")
    fact_type: str = Field(
        default="confirmed_fact",
        description="Fact type: decision, rejected_alternative, constraint, interface_contract, validation_result",
    )
    title: str = Field(..., description="Summary title")
    content: str = Field(..., description="Detailed content")
    target_components: list[str] = Field(
        default_factory=list, description="Target components or modules"
    )
    reason_or_constraint: str = Field(
        default="", description="Rationale, physical constraint, or rejection cause"
    )
    promotion_stage: str = Field(
        default="confirmed_fact",
        description="Initial stage: observation, project_event, confirmed_fact, knowledge, skill",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Metadata dictionary"
    )


class LivingFactListResponseDTO(BaseModel):
    """Response containing a list of living facts for a project."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    total_count: int = Field(..., ge=0, description="Total count of facts returned")
    facts: list[LivingFactDTO] = Field(default_factory=list, description="List of living facts")


class ContextProjectionRequestDTO(BaseModel):
    """Request payload to project an optimized context slice for a specific task."""

    model_config = ConfigDict(extra="forbid")

    target_task: str = Field(..., description="Task prompt or user goal description")
    target_components: list[str] = Field(
        default_factory=list, description="Target components or file paths involved"
    )
    token_budget: int = Field(
        default=1500, ge=100, le=32000, description="Max token budget for projected block"
    )


class ContextProjectionResponseDTO(BaseModel):
    """Response payload containing four-tier projected context slice."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    formatted_prompt_block: str = Field(
        ..., description="Markdown block formatted for direct agent context injection"
    )
    total_tokens_estimated: int = Field(
        ..., ge=0, description="Estimated token count of the formatted block"
    )
    facts: list[LivingFactDTO] = Field(
        default_factory=list, description="Facts included in the projected slice"
    )
    projected_by_tier: dict[str, int] = Field(
        default_factory=dict, description="Statistics of facts selected by each tier"
    )


class ValidationAuditRequestDTO(BaseModel):
    """Request payload to audit deterministic validation outcomes for a fact."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Fact identifier under evaluation")
    passed: bool = Field(..., description="True if verification/test passed with zero regressions")
    test_summary: str = Field(
        default="", description="Deterministic test report or verification conclusion"
    )


class ValidationAuditResponseDTO(BaseModel):
    """Response payload reflecting validation audit outcome and promotion status."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Audited fact identifier")
    new_stage: str = Field(..., description="Updated promotion stage")
    validation_count: int = Field(..., ge=0, description="Updated validation success count")
    regression_count: int = Field(..., ge=0, description="Updated regression failure count")
    is_promoted: bool = Field(..., description="True if fact advanced along the promotion ladder")
    recommend_skill_extraction: bool = Field(
        ..., description="True if fact has stabilized sufficiently to recommend skill creation"
    )
    message: str = Field(default="", description="Audit status message")
