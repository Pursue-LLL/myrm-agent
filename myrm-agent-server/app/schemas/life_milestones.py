"""Data transfer objects for Life Milestones and Personal Timeline API.

[POS]
Defines Pydantic request/response contracts for life milestones, evolving value nodes,
non-utilitarian growth reflections, and empathetic context projections.

[INPUT]
- typing, pydantic

[OUTPUT]
- RecordMilestoneRequest, MilestoneResponseDTO
- RegisterEraRequest, EraResponseDTO
- RegisterValueRequest, EvolveValueRequest, ValueResponseDTO
- RecordDiaryRequest, DiaryResponseDTO
- ProjectContextRequest, ContextProjectionResponseDTO
- RetrospectiveCardResponseDTO, LifeMilestonesStatsResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecordMilestoneRequest(BaseModel):
    """Payload to register a new life milestone."""

    milestone_id: str | None = Field(default=None, description="Optional explicit milestone identifier")
    timestamp_str: str = Field(min_length=4, description="Event date or timeframe string (e.g. '2021-08-15')")
    year: int = Field(ge=1900, le=2100, description="Calendar year of the event")
    category: str = Field(description="Domain category (career, education, relocation, family_life, etc.)")
    title: str = Field(min_length=2, description="Concise title of the milestone")
    narrative: str = Field(min_length=2, description="Detailed narrative of what transpired")
    long_term_impact: str = Field(min_length=2, description="Long-term life trajectory shifts")
    core_values: list[str] = Field(default_factory=list, description="Associated values or beliefs")
    intimacy_level: str = Field(default="open_overview", description="Privacy boundary: open_overview, intimate_personal, confidential_restricted")
    significance_score: float = Field(default=0.85, ge=0.0, le=1.0, description="Life significance impact weight")
    location: str | None = Field(default=None, description="City or place where milestone occurred")
    is_user_explicit: bool = Field(default=True, description="Whether explicitly submitted by the user")


class MilestoneResponseDTO(BaseModel):
    """Data transfer representation of a life milestone."""

    milestone_id: str
    timestamp_str: str
    year: int
    category: str
    title: str
    narrative: str
    long_term_impact: str
    core_values: list[str]
    intimacy_level: str
    significance_score: float
    location: str | None = None


class RegisterEraRequest(BaseModel):
    """Payload to define a macro life stage era."""

    era_id: str = Field(min_length=1, description="Unique era segment identifier")
    label: str = Field(min_length=2, description="Era title (e.g. '大学探索期', '创业起步期')")
    start_year: int = Field(ge=1900, le=2100, description="Beginning year of era")
    end_year: int | None = Field(default=None, ge=1900, le=2100, description="Ending year, or None if ongoing")
    guiding_philosophy: str = Field(min_length=2, description="Dominant life philosophy of this era")


class EraResponseDTO(BaseModel):
    """Data transfer representation of a lifecycle era."""

    era_id: str
    label: str
    start_year: int
    end_year: int | None = None
    guiding_philosophy: str


class RegisterValueRequest(BaseModel):
    """Payload to register a guiding value belief."""

    value_id: str | None = Field(default=None, description="Optional unique value identifier")
    theme: str = Field(min_length=1, description="Belief theme (e.g. 'work_life_balance', 'risk_philosophy')")
    current_stance: str = Field(min_length=2, description="Current guiding stance and belief")
    prior_belief: str | None = Field(default=None, description="Previous stance held before transformation")
    transition_catalyst: str | None = Field(default=None, description="What prompted the value shift")
    trigger_milestone_ids: list[str] = Field(default_factory=list, description="Referenced life milestones")
    effective_since_year: int = Field(ge=1900, le=2100, description="Year this stance became dominant")
    weight: float = Field(default=1.0, ge=0.1, le=2.0, description="Influence weight")


class EvolveValueRequest(BaseModel):
    """Payload to evolve an existing value into a new stance with causal linkage."""

    prior_value_id: str = Field(min_length=1, description="Identifier of the prior value node being superseded")
    new_value_id: str | None = Field(default=None, description="Optional identifier for the evolved node")
    theme: str = Field(min_length=1, description="Belief theme")
    new_stance: str = Field(min_length=2, description="Evolved new stance")
    transition_catalyst: str = Field(min_length=2, description="Catalyst or reason for the transformation")
    effective_since_year: int = Field(ge=1900, le=2100, description="Year this new stance took effect")
    trigger_milestone_ids: list[str] = Field(default_factory=list, description="Referenced milestone IDs")


class ValueResponseDTO(BaseModel):
    """Data transfer representation of a value belief."""

    value_id: str
    theme: str
    current_stance: str
    prior_belief: str | None = None
    transition_catalyst: str | None = None
    trigger_milestone_ids: list[str] = Field(default_factory=list)
    effective_since_year: int
    is_active: bool
    weight: float


class RecordDiaryRequest(BaseModel):
    """Payload to record a non-utilitarian personal reflection diary entry."""

    entry_id: str | None = Field(default=None, description="Optional unique diary identifier")
    emotional_state: str = Field(min_length=1, description="Emotional state or mind mood")
    reflection_text: str = Field(min_length=2, description="Self-reflective narrative text")
    linked_milestone_id: str | None = Field(default=None, description="Optional linked milestone")
    era_label: str | None = Field(default=None, description="Life era stage label")


class DiaryResponseDTO(BaseModel):
    """Data transfer representation of a growth reflection diary entry."""

    entry_id: str
    timestamp: str
    emotional_state: str
    reflection_text: str
    linked_milestone_id: str | None = None
    era_label: str | None = None


class ProjectContextRequest(BaseModel):
    """Payload to generate empathetic context projection for a user query."""

    query_text: str = Field(min_length=1, description="User query or situation narrative")
    max_intimacy: str = Field(default="intimate_personal", description="Max permitted privacy level")
    force_projection: bool = Field(default=False, description="Whether to bypass intent detection")


class ContextProjectionResponseDTO(BaseModel):
    """Projected context prompt injection payload."""

    projected_text: str
    relevant_milestone_count: int
    active_values: list[str]
    applied_intimacy_level: str


class RetrospectiveCardResponseDTO(BaseModel):
    """Synthesized reflective life retrospective card."""

    era_label: str
    time_span: str
    milestone_highlights: list[str]
    dominant_values: list[str]
    growth_reflections: list[str]
    companion_empathy_note: str


class LifeMilestonesStatsResponse(BaseModel):
    """Statistical overview of lifelong personal memory assets."""

    total_milestones: int
    total_eras: int
    active_values: int
    total_diaries: int
