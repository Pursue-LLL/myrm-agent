# [POS]: app/schemas/hybrid_memory.py
# [INPUT]: Pydantic BaseModel, Field, and typing primitives
# [OUTPUT]: Request and response DTO schemas for zero-config dual-drive hybrid memory

from __future__ import annotations

from pydantic import BaseModel, Field


class HybridMemoryItemDTO(BaseModel):
    """Memory item payload stored in the hybrid FTS5 engine."""

    item_id: str = Field(description="Unique identifier for the memory item")
    content: str = Field(description="Full text body of the memory item")
    title: str = Field(default="", description="Optional title or headline")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Arbitrary typed metadata")
    created_at: str = Field(default="", description="ISO timestamp")


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


class HybridSearchResultDTO(BaseModel):
    """Individual hit from hybrid retrieval."""

    item_id: str = Field(description="Memory item identifier")
    title: str = Field(description="Item title")
    content: str = Field(description="Matched text content")
    score: float = Field(description="BM25 or RRF relevance score")
    source_channel: str = Field(description="Channel: fts, vector, rrf_hybrid, or fts_degraded")
    rank: int = Field(ge=1, description="Rank position in final result list")
    matched_terms: list[str] = Field(default_factory=list, description="Expanded synonym or matched terms")


class HybridSearchResponseDTO(BaseModel):
    """Complete response returned by hybrid search."""

    query: str = Field(description="Original search query")
    mode: str = Field(description="Active retrieval mode: fts_only, dense_only, hybrid_rrf, or degraded_fallback")
    total_hits: int = Field(ge=0, description="Count of returned items")
    results: list[HybridSearchResultDTO] = Field(default_factory=list, description="Ranked result list")


class RegisterSynonymsRequestDTO(BaseModel):
    """Payload to register an offline synonym cluster."""

    primary_term: str = Field(min_length=1, description="Anchor keyword")
    synonyms: list[str] = Field(min_length=1, description="List of synonym expressions")


class RegisterSynonymsResponseDTO(BaseModel):
    """Confirmation of synonym registration."""

    primary_term: str = Field(description="Anchor keyword")
    total_synonyms: int = Field(ge=0, description="Total active synonyms associated with this term")
    is_success: bool = Field(description="True if registered successfully")


class HybridEngineStatsDTO(BaseModel):
    """Operational telemetry and status snapshot."""

    total_items: int = Field(ge=0, description="Total rows in SQLite FTS5 table")
    synonym_terms_count: int = Field(ge=0, description="Unique keyword nodes in synonym graph")
    dense_vector_available: bool = Field(description="True if dense vector provider is configured")
    active_mode: str = Field(description="Default active retrieval mode")
    db_path: str = Field(description="Underlying SQLite database path")
    last_updated: str = Field(description="Timestamp of telemetry snapshot")
