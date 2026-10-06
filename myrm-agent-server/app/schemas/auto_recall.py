"""
[POS] app/schemas/auto_recall.py
[INPUT] pydantic
[OUTPUT] RecallCandidateDTO, AutoRecallEvaluateRequest, AutoRecallDecisionResponse, SlidingWindowStatsResponse, SessionClearResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RecallCandidateDTO(BaseModel):
    """Memory or experience candidate representation."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., min_length=1, description="Unique memory item identifier")
    content: str = Field(..., min_length=1, description="Memory textual content")
    initial_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Rough initial retrieval score")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Arbitrary typed metadata attributes"
    )


class AutoRecallEvaluateRequest(BaseModel):
    """Payload to trigger experience auto-recall evaluation across lifecycle gates."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Session identifier for multi-turn tracking")
    current_turn: int = Field(default=1, ge=1, description="Current conversational turn index")
    raw_candidates: list[RecallCandidateDTO] = Field(
        default_factory=list, description="Raw candidates retrieved from rough store"
    )
    event_name: str | None = Field(default=None, description="Explicit lifecycle event if present")
    tool_name: str | None = Field(default=None, description="Name of tool intended for invocation")
    query_text: str | None = Field(default=None, description="User query or context prompt")
    force_recall: bool = Field(default=False, description="Whether to bypass trigger classification")


class AutoRecallDecisionResponse(BaseModel):
    """Aggregated decision payload produced by ExperienceRecallGate."""

    model_config = ConfigDict(extra="forbid")

    triggered: bool = Field(..., description="Whether sensitive trigger was activated")
    trigger_type: str = Field(..., description="Classified trigger type")
    candidates_pre_dedup: int = Field(ge=0, description="Candidate count before deduplication")
    candidates_post_dedup: int = Field(ge=0, description="Candidate count surviving 5-turn sliding window")
    injected_candidates: list[RecallCandidateDTO] = Field(
        default_factory=list, description="Final ranked memory items injected into prompt"
    )
    reranker_status: str = Field(..., description="Status of neural reranker stage")
    audit_reason: str = Field(..., description="Detailed audit reason")


class SlidingWindowStatsResponse(BaseModel):
    """Statistics detailing multi-turn sliding window deduplication state."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    active_window_turns: int = Field(ge=0, description="Number of active turns tracked in window")
    total_suppressed_id_count: int = Field(ge=0, description="Count of distinct suppressed memory IDs")


class SessionClearResponse(BaseModel):
    """Response returned upon clearing a session's sliding window cache."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1)
    cleared: bool = Field(...)
