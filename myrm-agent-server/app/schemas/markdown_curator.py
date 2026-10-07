# [POS]: app/schemas/markdown_curator.py
# [INPUT]: None (Pydantic models for Markdown Curator Studio)
# [OUTPUT]: CuratedMemoryEntryDTO, CurateEntryRequest, UpdateCurateEntryRequest, AuditEntryRequest, MarkdownSyncRequest, MarkdownSyncResponseDTO, CuratorStudioSummaryDTO

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CuratedMemoryEntryDTO(BaseModel):
    """DTO representing a human-readable curated memory unit."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    category: str = Field(..., description="Category: preference, fact, procedure, experience")
    title: str
    content: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(
        default="confirmed",
        description="Status: confirmed, pending_confirmation, rejected, archived",
    )
    tags: list[str] = Field(default_factory=list)
    source_session_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CurateEntryRequest(BaseModel):
    """Request payload to create a new curated memory entry."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(default="fact", description="Category: preference, fact, procedure, experience")
    title: str = Field(..., description="Short recognizable title")
    content: str = Field(..., description="Descriptive text body")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: str = Field(default="confirmed", description="Initial status")
    tags: list[str] = Field(default_factory=list)
    source_session_id: str | None = None


class UpdateCurateEntryRequest(BaseModel):
    """Request payload to edit an existing curated memory entry."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    content: str | None = None
    category: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class AuditEntryRequest(BaseModel):
    """Request payload to approve or reject a memory candidate."""

    model_config = ConfigDict(extra="forbid")

    is_approved: bool = Field(..., description="True to confirm, False to reject")


class MarkdownSyncRequest(BaseModel):
    """Request payload containing raw Markdown to synchronize with the in-memory store."""

    model_config = ConfigDict(extra="forbid")

    markdown_text: str = Field(..., description="Markdown document text to sync from")
    hard_delete: bool = Field(
        default=False,
        description="True to hard purge deleted items, False to mark as archived",
    )


class MarkdownSyncResponseDTO(BaseModel):
    """Response payload detailing changes resulting from Markdown synchronization."""

    model_config = ConfigDict(extra="forbid")

    added_count: int
    updated_count: int
    deleted_count: int
    added_entries: list[CuratedMemoryEntryDTO]
    updated_entries: list[CuratedMemoryEntryDTO]
    deleted_entry_ids: list[str]


class CuratorStudioSummaryDTO(BaseModel):
    """Response payload reporting metrics across curated memory entries."""

    model_config = ConfigDict(extra="forbid")

    total_entries: int
    confirmed_count: int
    pending_count: int
    rejected_count: int
    archived_count: int
    categories_breakdown: dict[str, int]
