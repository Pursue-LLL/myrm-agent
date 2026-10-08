"""Pydantic V2 schemas for retrieval score honesty API endpoints.

[POS]
Data transfer objects and request/response models for retrieval score honesty,
separating raw physical similarity from composite ranking scores.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- CandidateEvaluationItem
- DualThresholdConfigDTO
- ScoreBreakdownDTO
- ThresholdEvaluationVerdictDTO
- HonestCandidateResponseDTO
- ScoreHonestyStatsDTO
- EvaluateCandidatesRequest
- EvaluateCandidatesResponse
- FilterCandidatesResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateEvaluationItem(BaseModel):
    """Input candidate for score honesty evaluation."""

    id: str = Field(description="Unique candidate identifier")
    content: str = Field(description="Memory text content")
    raw_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description="Physical cosine similarity",
    )
    recency_factor: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Recency multiplier or boost",
    )
    importance_boost: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="Importance weight boost",
    )
    mmr_penalty: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="MMR diversity penalty",
    )
    rrf_score: float = Field(
        default=0.0,
        ge=0.0,
        description="Reciprocal rank fusion score",
    )
    metadata: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Arbitrary structured tags",
    )


class DualThresholdConfigDTO(BaseModel):
    """Dual threshold parameters DTO."""

    raw_similarity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Floor applied to physical vector store similarity",
    )
    ranking_score_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Floor applied to composite ranking score after pipeline",
    )
    strict_mode: bool = Field(
        default=True,
        description="If True, candidate must pass both gates",
    )


class ScoreBreakdownDTO(BaseModel):
    """Attribution breakdown factors."""

    raw_similarity: float
    recency_factor: float
    importance_boost: float
    mmr_penalty: float
    rrf_score: float
    final_ranking_score: float
    explanation: str


class ThresholdEvaluationVerdictDTO(BaseModel):
    """Decision verdict DTO."""

    passed_raw: bool
    passed_ranking: bool
    admitted: bool
    rejection_stage: str
    rejection_reason: str | None = None


class HonestCandidateResponseDTO(BaseModel):
    """Evaluated candidate output."""

    id: str
    content: str
    raw_similarity: float
    ranking_score: float
    breakdown: ScoreBreakdownDTO
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    verdict: ThresholdEvaluationVerdictDTO | None = None


class ScoreHonestyStatsDTO(BaseModel):
    """Aggregated stats DTO."""

    total_candidates: int
    admitted_count: int
    rejected_count: int
    raw_admitted_count: int
    ranking_admitted_count: int
    both_passed_count: int
    divergence_count: int
    divergence_rate: float
    mean_raw_similarity: float
    mean_ranking_score: float


class EvaluateCandidatesRequest(BaseModel):
    """Request payload for evaluating a batch of candidates."""

    candidates: list[CandidateEvaluationItem]
    config: DualThresholdConfigDTO | None = None


class EvaluateCandidatesResponse(BaseModel):
    """Response payload for evaluated candidates and stats."""

    evaluated: list[HonestCandidateResponseDTO]
    stats: ScoreHonestyStatsDTO


class FilterCandidatesResponse(BaseModel):
    """Response payload returning only admitted candidates."""

    admitted: list[HonestCandidateResponseDTO]
    total_admitted: int
