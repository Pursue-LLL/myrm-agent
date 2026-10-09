"""[POS]: app/schemas/lifecycle_hotness.py
[INPUT]: Timestamp parameters, access frequencies, and memory payloads for lifecycle hotness API.
[OUTPUT]: Strongly typed Pydantic models for hotness scoring, exponential time decay, and blended reranking.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HotnessLifecycleStageAPI(StrEnum):
    """Lifecycle classification of memory records based on hotness score."""

    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


class MemoryLifecycleItemPayload(BaseModel):
    """Single memory item payload with telemetry and scores."""

    id: str = Field(..., description="Unique memory identifier or URI")
    active_count: int = Field(default=0, ge=0, description="Cumulative access or retrieval count")
    updated_at: datetime | None = Field(
        default=None,
        description="Last updated or retrieved timestamp (UTC)",
    )
    semantic_score: float = Field(default=0.0, ge=0.0, description="Raw semantic retrieval score")
    hotness_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Computed hotness score [0.0, 1.0]")
    blended_score: float = Field(default=0.0, ge=0.0, description="Blended score combining semantic and hotness")
    lifecycle_stage: HotnessLifecycleStageAPI = Field(
        default=HotnessLifecycleStageAPI.WARM,
        description="Assigned lifecycle stage",
    )
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class SingleScoreRequest(BaseModel):
    """Request payload to compute hotness score for a single entity."""

    active_count: int = Field(default=0, ge=0, description="Access or retrieval frequency")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")
    half_life_days: float = Field(default=7.0, gt=0.0, le=365.0, description="Configured half-life in days")
    now: datetime | None = Field(default=None, description="Current time override for deterministic testing")


class SingleScoreResponse(BaseModel):
    """Response payload returning computed hotness score and lifecycle classification."""

    active_count: int = Field(..., description="Echoed access count")
    updated_at: datetime | None = Field(default=None, description="Echoed update timestamp")
    hotness_score: float = Field(..., description="Computed hotness score [0.0, 1.0]")
    lifecycle_stage: HotnessLifecycleStageAPI = Field(..., description="Classified lifecycle stage")


class BlendRerankRequest(BaseModel):
    """Request payload to execute blended reranking between semantic similarity and hotness."""

    items: list[MemoryLifecycleItemPayload] = Field(..., description="List of candidate memory items")
    blend_alpha: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Weight alpha for hotness score: (1-alpha)*semantic + alpha*hotness",
    )
    half_life_days: float = Field(default=7.0, gt=0.0, le=365.0, description="Half-life decay in days")
    now: datetime | None = Field(default=None, description="Current time override")


class BlendRerankResponse(BaseModel):
    """Response payload containing reranked items and batch summary telemetry."""

    items: list[MemoryLifecycleItemPayload] = Field(default_factory=list, description="Reranked memory items")
    cold_count: int = Field(default=0, ge=0, description="Total cold items")
    warm_count: int = Field(default=0, ge=0, description="Total warm items")
    hot_count: int = Field(default=0, ge=0, description="Total hot items")
    avg_hotness: float = Field(default=0.0, ge=0.0, le=1.0, description="Average hotness score across batch")
