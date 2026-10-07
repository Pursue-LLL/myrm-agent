"""[POS]: app/schemas/four_tier_fts.py
[INPUT]: Pydantic BaseModel, Field, datetime, and typing primitives.
[OUTPUT]: Request and response DTO schemas for four-tier persistent memory, SQLite FTS5 search, and dream compaction.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FourTierMemoryItemDTO(BaseModel):
    """Four-tier persistent memory item across project, session, progress, or global scope."""

    item_id: str = Field(description="Unique identifier of the memory item")
    scope: str = Field(description="Scope tier: project, session, progress, or global")
    title: str = Field(description="Short title or classification headline")
    content: str = Field(description="Detailed persistent text content")
    project_hash: str = Field(default="default", description="Repository or project scope partition hash")
    session_id: str = Field(default="", description="Chat or workflow session ID context")
    tags: list[str] = Field(default_factory=list, description="Categorization and classification tags")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last updated timestamp")


class SaveFourTierMemoryRequestDTO(BaseModel):
    """Payload to record or update a four-tier persistent memory item."""

    scope: str = Field(description="Scope tier: project, session, progress, or global")
    title: str = Field(description="Title headline for identification")
    content: str = Field(description="Memory content text")
    project_hash: str = Field(default="default", description="Repository or project scope partition hash")
    session_id: str = Field(default="", description="Chat or workflow session ID context")
    tags: list[str] = Field(default_factory=list, description="Optional classification tags")
    item_id: str | None = Field(default=None, description="Optional custom item ID")


class FtsSearchResultDTO(BaseModel):
    """Result item returned by SQLite FTS5 BM25 search."""

    item_id: str = Field(description="Matched memory item ID")
    scope: str = Field(description="Scope tier")
    project_hash: str = Field(description="Project partition hash")
    title: str = Field(description="Item title")
    content: str = Field(description="Item full content")
    snippet: str = Field(description="Extracted matched text snippet")
    bm25_rank: float = Field(description="FTS5 BM25 relevance score")
    updated_at: datetime = Field(description="Last update timestamp")


class DreamCompactionReportDTO(BaseModel):
    """Outcome report of background dreaming compaction and maintenance."""

    dream_id: str = Field(description="Unique dream compaction cycle ID")
    scanned_items_count: int = Field(ge=0, description="Total memory items scanned")
    merged_items_count: int = Field(ge=0, description="Number of duplicate or fragmented items merged")
    pruned_items_count: int = Field(ge=0, description="Number of stale items pruned")
    retained_items_count: int = Field(ge=0, description="Active items remaining after compaction")
    duration_ms: float = Field(ge=0.0, description="Execution duration in milliseconds")
    created_at: datetime = Field(description="Cycle timestamp")


class RunDreamCompactionRequestDTO(BaseModel):
    """Request payload to trigger dream compaction cycle."""

    project_hash: str = Field(default="default", description="Project hash partition to compact")
    purge_progress_days: int = Field(default=7, ge=1, description="Days after which inactive progress memories are pruned")
