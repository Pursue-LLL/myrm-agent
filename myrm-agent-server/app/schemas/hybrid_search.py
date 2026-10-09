"""Data transfer objects for dual-engine hybrid search and graceful fallback API.

[POS]
Pydantic contracts for hybrid FTS + vector querying, multi-factor re-ranking,
circuit breaker state telemetry, and graceful fallback reporting.

[INPUT]
- typing, pydantic

[OUTPUT]
- HybridSearchHitDTO, HybridSearchQueryDTO, HybridSearchReportDTO
- HybridSearchResponseDTO, CircuitBreakerStatusDTO, ResetCircuitBreakerResponseDTO
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HybridSearchHitDTO(BaseModel):
    """Data transfer representation of a candidate hit fused from FTS/Vector engines."""

    item_id: str = Field(description="Unique identifier of retrieved document")
    title: str = Field(description="Document title or brief header")
    content: str = Field(description="Body content snippet")
    score: float = Field(ge=0.0, description="Final fused and re-ranked relevance score")
    vector_score: float = Field(default=0.0, ge=0.0, description="Raw cosine/vector similarity")
    text_score: float = Field(default=0.0, ge=0.0, description="Normalized BM25 text score")
    created_at: str = Field(default="", description="ISO-8601 creation timestamp for temporal decay")
    exact_match: bool = Field(default=False, description="Whether exact search phrase was matched")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom document attributes")


class HybridSearchQueryDTO(BaseModel):
    """Payload specifying dual-engine hybrid retrieval constraints."""

    query_text: str = Field(min_length=1, description="Raw natural language search query")
    top_k: int = Field(default=10, gt=0, le=100, description="Maximum number of hits to return")
    min_score: float = Field(default=0.20, ge=0.0, le=1.0, description="Relevance cutoff threshold")
    vector_weight: float = Field(default=0.65, ge=0.0, le=1.0, description="Weight multiplier for vector score")
    text_weight: float = Field(default=0.35, ge=0.0, le=1.0, description="Weight multiplier for BM25 score")
    recency_half_life_days: float = Field(
        default=30.0, gt=0.0, description="Half-life decay in days for temporal recency"
    )
    importance_multiplier: float = Field(
        default=1.0, ge=0.0, le=5.0, description="Relevance multiplier for critical facts"
    )
    exact_phrase_boost: float = Field(
        default=1.5, ge=1.0, le=3.0, description="Boost multiplier applied when exact phrase matches"
    )
    mmr_lambda: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Diversity parameter: 1.0 = pure relevance, 0.0 = maximal diversity"
    )
    max_tokens: int = Field(default=4000, gt=0, description="Upper bound token budget across returned hits")
    timeout_seconds: float = Field(
        default=2.0, gt=0.0, le=30.0, description="Strict timeout threshold for remote vector engine"
    )


class HybridSearchReportDTO(BaseModel):
    """Audit report telemetry for search execution path and latency breakdown."""

    query_text: str = Field(description="Executed query string")
    mode: Literal["hybrid", "full_hybrid", "fallback_fts", "vector_only", "fts_only"] = Field(
        description="Effective execution mode"
    )
    fallback_reason: Literal[
        "none", "circuit_open", "provider_timeout", "provider_error", "provider_unconfigured"
    ] = Field(default="none", description="Reason if fallback was triggered")
    total_hits: int = Field(ge=0, description="Number of results surviving threshold and MMR")
    total_latency_ms: float = Field(ge=0.0, description="Total wall-clock latency in milliseconds")
    vector_latency_ms: float = Field(ge=0.0, description="Time spent querying vector provider in milliseconds")
    fts_latency_ms: float = Field(ge=0.0, description="Time spent querying local FTS provider in milliseconds")
    circuit_state: Literal["closed", "open", "half_open"] = Field(
        description="Current tri-state circuit breaker status"
    )


class HybridSearchResponseDTO(BaseModel):
    """Envelope containing retrieved hits and execution telemetry report."""

    hits: list[HybridSearchHitDTO] = Field(description="Ranked candidate hits")
    report: HybridSearchReportDTO = Field(description="Telemetry and fallback audit report")


class CircuitBreakerStatusDTO(BaseModel):
    """Telemetry representation of current vector engine circuit breaker."""

    state: Literal["closed", "open", "half_open"] = Field(description="Circuit breaker state")
    failure_count: int = Field(ge=0, description="Consecutive failure count")
    failure_threshold: int = Field(gt=0, description="Failure threshold tripping breaker")
    recovery_timeout_seconds: float = Field(gt=0.0, description="Recovery cooldown duration")


class ResetCircuitBreakerResponseDTO(BaseModel):
    """Response returned upon manually resetting the circuit breaker."""

    success: bool = Field(description="Whether the reset was acknowledged")
    message: str = Field(description="Status description message")
    current_state: Literal["closed", "open", "half_open"] = Field(description="Effective breaker state")
