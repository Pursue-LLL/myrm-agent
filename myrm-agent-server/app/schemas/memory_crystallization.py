"""
[POS] app/schemas/memory_crystallization.py
[INPUT] pydantic
[OUTPUT] EvaluateFormationRequestDTO, EvaluateFormationResponseDTO, CrystallizedRuleMetricsDTO, FilterFacetsRequestDTO, FilterFacetsResponseDTO, RecordFeedbackRequestDTO, RecordFeedbackResponseDTO

Pydantic DTOs for Procedural Memory Crystallization Lifecycle and Self-Correction Governor.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvaluateFormationRequestDTO(BaseModel):
    """Payload to evaluate formation-stage two-factor importance gate."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence factor")
    severity: float = Field(..., ge=0.0, le=1.0, description="Error severity or behavioral consequence factor")
    content: str = Field(default="", description="Procedural rule text or instruction being evaluated")


class EvaluateFormationResponseDTO(BaseModel):
    """Outcome of formation-stage importance evaluation."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(..., description="Normalized confidence factor")
    severity: float = Field(..., description="Normalized severity factor")
    importance: float = Field(..., description="Composite importance score = confidence * severity")
    passed_gate: bool = Field(..., description="Whether importance exceeds 0.70 threshold")
    gate_reason: str = Field(..., description="Human-readable decision explanation")


class CrystallizedRuleMetricsDTO(BaseModel):
    """Telemetry tracking rule operational state and dynamic scheduling weight."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule identifier")
    facets: list[str] = Field(default_factory=lambda: ["global"], description="Domain and role scopes")
    success_count: int = Field(default=0, ge=0, description="Execution success count")
    fail_count: int = Field(default=0, ge=0, description="Execution failure count")
    win_rate: float = Field(default=1.0, ge=0.0, le=1.0, description="Empirical win rate ratio")
    state: str = Field(..., description="Lifecycle state: active, degraded, or retired")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Dynamic injection scheduling weight")
    description: str = Field(default="", description="Rule explanation or summary")


class FilterFacetsRequestDTO(BaseModel):
    """Payload to filter candidate rules by active operational facets."""

    model_config = ConfigDict(extra="forbid")

    rules: list[CrystallizedRuleMetricsDTO] = Field(..., description="Candidate rule metrics to filter")
    active_facets: list[str] = Field(default_factory=lambda: ["global"], description="Active operational domain facets")


class FilterFacetsResponseDTO(BaseModel):
    """Result of facet-scoped rule filtering."""

    model_config = ConfigDict(extra="forbid")

    active_facets: list[str] = Field(..., description="Operational facets applied during filtering")
    matched_rules: list[CrystallizedRuleMetricsDTO] = Field(..., description="Active rules matching active facets")
    total_candidates: int = Field(..., description="Total input candidates evaluated")
    matched_count: int = Field(..., description="Count of matched active rules")


class RecordFeedbackRequestDTO(BaseModel):
    """Payload to record rule execution feedback and update lifecycle state."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., min_length=1, description="Target rule identifier")
    session_id: str = Field(..., min_length=1, description="Active session ID to trace repeat failures")
    is_success: bool = Field(..., description="Whether the action using this rule succeeded")
    secondary_error_occurred: bool = Field(default=False, description="Whether repeat failure occurred in same session")
    description: str = Field(default="", description="Optional updated description")
    facets: list[str] | None = Field(default=None, description="Optional domain facets for initial registration")


class RecordFeedbackResponseDTO(BaseModel):
    """Result of feedback processing with updated telemetry."""

    model_config = ConfigDict(extra="forbid")

    metrics: CrystallizedRuleMetricsDTO = Field(..., description="Updated rule telemetry and lifecycle state")
    repeat_failure_penalized: bool = Field(..., description="Whether same-session repeat error penalty was applied")
