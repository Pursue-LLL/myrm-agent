"""Schemas for embedded SQLite vector engine API.

[POS]
Pydantic request and response contracts for the single-file embedded SQLite
vector engine and temporal decay retrieval endpoints.

[INPUT]
- pydantic (BaseModel, Field)

[OUTPUT]
- SqliteVecStatsResponse: Database and engine operational metrics
- SqliteVecSearchRequest: Vector search request with temporal decay parameters
- SqliteVecSearchItem: Enriched retrieved memory item
- SqliteVecSearchResponse: Search results container
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SqliteVecStatsResponse(BaseModel):
    """Engine operational and storage statistics."""

    engine_mode: str = Field(description="Active execution mode: native_vec0 or process_blob.")
    is_persistent: bool = Field(description="Whether database storage is persistent on disk.")
    db_path: str = Field(description="Resolved SQLite database filesystem path.")
    file_size_bytes: int = Field(description="Database file size on disk in bytes.")
    collection_count: int = Field(description="Total number of registered vector collections.")
    total_documents: int = Field(description="Total number of stored vector documents.")
    status: str = Field(default="healthy", description="Engine health status.")


class SqliteVecSearchRequest(BaseModel):
    """Query payload for vector search with optional temporal decay."""

    collection: str = Field(default="agent_memory", description="Target collection name.")
    query_vector: list[float] = Field(description="Dense query embedding vector.")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum items to return.")
    apply_decay: bool = Field(default=True, description="Whether to apply exponential time decay.")
    half_life_seconds: float | None = Field(
        default=None,
        ge=60.0,
        description="Optional custom half life in seconds overriding default.",
    )
    score_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum score threshold for returned results.",
    )


class SqliteVecSearchItem(BaseModel):
    """Single retrieved memory document item."""

    id: str = Field(description="Document unique ID.")
    content: str = Field(description="Document content.")
    score: float = Field(description="Similarity score (decayed if apply_decay is true).")
    raw_similarity: float | None = Field(default=None, description="Pre-decay cosine similarity.")
    decay_factor: float | None = Field(default=None, description="Applied time decay factor.")
    metadata: dict[str, str | int | float | bool | list[str]] = Field(
        default_factory=dict, description="Document metadata."
    )


class SqliteVecSearchResponse(BaseModel):
    """Response payload containing matching vector documents."""

    collection: str = Field(description="Queried collection.")
    count: int = Field(description="Number of items returned.")
    items: list[SqliteVecSearchItem] = Field(description="Retrieved ranked items.")
