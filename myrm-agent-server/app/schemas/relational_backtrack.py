"""Pydantic schemas for temporal relation triplets and cross-session relational backtracking.

[INPUT]
- pydantic::{BaseModel, ConfigDict, Field} (POS: validated request and response models)

[OUTPUT]
- TemporalRelationTripletDTO, RecordTripletRequest, RecordTripletResponse: triplet record and its registration
- RelationalBacktrackQueryRequest, RelationalBacktrackHitDTO, RelationalBacktrackResponseDTO: backtrack query and scored hits with an inferred answer

[POS]
API contracts of relational backtracking, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TemporalRelationTripletDTO(BaseModel):
    """DTO representing a structured temporal relation triplet."""

    model_config = ConfigDict(extra="forbid")

    triplet_id: str
    subject: str
    predicate_action: str
    target_entity: str
    target_entity_type: str
    temporal_anchor: str
    session_id: str
    message_id: str
    verbatim_quote: str
    action_synonyms: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: str | None = None


class RecordTripletRequest(BaseModel):
    """Request payload to register a new temporal relation triplet."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(default="user", description="Subject performing the action")
    predicate_action: str = Field(..., description="Canonical action or event, e.g. 'eat_hotpot'")
    target_entity: str = Field(..., description="Target entity name, e.g. '李总'")
    target_entity_type: str = Field(
        default="client",
        description="Entity type category: person, client, project, organization, location, tool",
    )
    temporal_anchor: str = Field(..., description="Absolute or relative date anchor, e.g. '2026-10-15'")
    session_id: str = Field(..., description="Originating session identifier")
    message_id: str = Field(..., description="Originating message identifier")
    verbatim_quote: str = Field(..., description="Exact quoted text fragment pinning the assertion")
    action_synonyms: list[str] = Field(default_factory=list, description="Associated synonyms, e.g. ['吃火锅', '打边炉']")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RecordTripletResponse(BaseModel):
    """Response returned upon successfully storing a temporal relation triplet."""

    model_config = ConfigDict(extra="forbid")

    is_success: bool = True
    triplet: TemporalRelationTripletDTO


class RelationalBacktrackQueryRequest(BaseModel):
    """Request payload for cross-session entity backtracking."""

    model_config = ConfigDict(extra="forbid")

    action_cue: str = Field(..., description="Action cue to search for, e.g. '打边炉', '签约'")
    target_entity_type: str | None = Field(default=None, description="Optional entity category filter")
    session_id_scope: str | None = Field(default=None, description="Optional session filter")
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RelationalBacktrackHitDTO(BaseModel):
    """A matched relational candidate returned by the backtrack engine."""

    model_config = ConfigDict(extra="forbid")

    triplet: TemporalRelationTripletDTO
    matched_cue: str
    match_score: float


class RelationalBacktrackResponseDTO(BaseModel):
    """Consolidated response returned from cross-session relational backtracking."""

    model_config = ConfigDict(extra="forbid")

    hits: list[RelationalBacktrackHitDTO]
    total_found: int
    inferred_answer: str | None
