"""Request and response DTO schemas for zero-config dual-drive hybrid memory and circuit-breaker telemetry.

[POS]
app/schemas/hybrid_memory.py

[INPUT]
- Pydantic BaseModel, Field, and typing primitives

[OUTPUT]
- Request and response DTO schemas for zero-config dual-drive hybrid memory and circuit-breaker telemetry
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CircuitBreakerStatsDTO(BaseModel):
    """Telemetry metrics snapshot of embedding circuit breaker."""

    state: str = Field(default="closed", description="Circuit breaker state: closed, open, or half_open")
    failure_count: int = Field(default=0, ge=0, description="Consecutive failure count")
    consecutive_successes: int = Field(default=0, ge=0, description="Consecutive probe successes")
    last_failure_time: float = Field(default=0.0, description="Epoch timestamp of last failure")
    tripped_count: int = Field(default=0, ge=0, description="Total times breaker tripped to open")


class AdaptiveRrfConfigDTO(BaseModel):
    """Configuration parameters for multi-factor Adaptive RRF."""

    rrf_k: int = Field(default=60, ge=1, le=500, description="RRF constant smoothing factor")
    fts_weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Weight multiplier for FTS5 BM25 rank")
    vector_weight: float = Field(default=1.0, ge=0.0, le=10.0, description="Weight multiplier for dense vector rank")
    importance_weight: float = Field(default=0.3, ge=0.0, le=5.0, description="Weight multiplier for cognitive importance")
    half_life_seconds: float = Field(default=86400.0, ge=0.0, description="Ebbinghaus memory recency half-life in seconds")
    apply_recency_decay: bool = Field(default=True, description="Whether to apply recency half-life decay")


class HybridMemoryItemDTO(BaseModel):
    """Memory item payload stored in the hybrid FTS5 engine."""

    item_id: str = Field(description="Unique identifier for the memory item")
    content: str = Field(description="Full text body of the memory item")
    title: str = Field(default="", description="Optional title or headline")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Arbitrary typed metadata")
    created_at: str = Field(default="", description="ISO timestamp")
    importance: float = Field(default=0.5, ge=0.0, le=1.0, description="Cognitive importance score [0.0, 1.0]")
    timestamp: float = Field(default=0.0, description="Epoch timestamp of item creation/modification")


class InsertHybridItemRequestDTO(BaseModel):
    """Payload to insert or update an item in hybrid memory."""

    item: HybridMemoryItemDTO = Field(description="Memory item to insert or update")


class InsertHybridItemResponseDTO(BaseModel):
    """Result of memory item insertion."""

    item_id: str = Field(description="Identifier of the stored item")
    is_success: bool = Field(description="True if stored successfully")


class HybridSearchRequestDTO(BaseModel):
    """Parameters for dual-drive hybrid search."""

    query: str = Field(min_length=1, description="Search query string")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of hits to return")
    enable_vector: bool = Field(default=True, description="True to invoke dense vector retrieval if available")
    adaptive_rrf: AdaptiveRrfConfigDTO | None = Field(default=None, description="Optional custom Adaptive RRF parameters")


class HybridSearchResultDTO(BaseModel):
    """Individual hit from hybrid retrieval."""

    item_id: str = Field(description="Memory item identifier")
    title: str = Field(description="Item title")
    content: str = Field(description="Matched text content")
    score: float = Field(description="BM25, vector, or RRF relevance score")
    source_channel: str = Field(description="Channel: fts, vector, rrf_hybrid, or fts_degraded")
    rank: int = Field(ge=1, description="Rank position in final result list")
    matched_terms: list[str] = Field(default_factory=list, description="Expanded synonym or matched terms")
    importance: float = Field(default=0.5, description="Item cognitive importance score")
    recency_factor: float = Field(default=1.0, description="Ebbinghaus recency decay multiplier applied")
    is_degraded: bool = Field(default=False, description="True if hit was served via degraded fallback")
    degradation_reason: str = Field(default="", description="Reason for degraded fallback if applicable")


class HybridSearchResponseDTO(BaseModel):
    """Complete response returned by hybrid search."""

    query: str = Field(description="Original search query")
    mode: str = Field(description="Active retrieval mode: fts_only, dense_only, hybrid_rrf, or degraded_fallback")
    total_hits: int = Field(ge=0, description="Count of returned items")
    results: list[HybridSearchResultDTO] = Field(default_factory=list, description="Ranked result list")


class HybridEngineStatsDTO(BaseModel):
    """Operational telemetry and status snapshot."""

    total_items: int = Field(ge=0, description="Total rows in SQLite FTS5 table")
    synonym_terms_count: int = Field(ge=0, description="Unique keyword nodes in synonym graph")
    dense_vector_available: bool = Field(description="True if dense vector provider is configured")
    active_mode: str = Field(description="Default active retrieval mode")
    db_path: str = Field(description="Underlying SQLite database path")
    circuit_breaker: CircuitBreakerStatsDTO = Field(default_factory=CircuitBreakerStatsDTO, description="Circuit breaker metrics")
    last_updated: str = Field(description="Timestamp of telemetry snapshot")


class TripCircuitBreakerRequestDTO(BaseModel):
    """Request payload to manually trip the circuit breaker."""

    reason: str = Field(default="manual_simulation", description="Reason for tripping circuit breaker")


class TripCircuitBreakerResponseDTO(BaseModel):
    """Response returned when circuit breaker is tripped."""

    is_success: bool = Field(description="True if trip operation was applied")
    state: str = Field(description="Resulting circuit breaker state")
    tripped_count: int = Field(description="Total count of trips")


class ResetCircuitBreakerResponseDTO(BaseModel):
    """Response returned when circuit breaker is reset."""

    is_success: bool = Field(description="True if reset operation was applied")
    state: str = Field(description="Resulting circuit breaker state")
