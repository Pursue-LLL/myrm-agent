"""[POS]: app/schemas/tombstone.py
[INPUT]: None.
[OUTPUT]: Pydantic schemas for memory tombstoning, contradiction curation, recall filtering, and eviction.
"""

from pydantic import BaseModel, Field


class TombstoneCandidateDTO(BaseModel):
    """Memory directive entry submitted for contradiction curation or recall filtering."""

    memory_id: str = Field(..., description="Unique memory directive identifier")
    content: str = Field(..., min_length=1, description="Textual directive content")
    category: str = Field(default="general", description="Cognitive category")
    created_at: float = Field(default=0.0, description="Creation timestamp")
    tags: list[str] = Field(default_factory=list, description="Associated tag labels")


class ContradictionPairDTO(BaseModel):
    """Pair of mutually conflicting memory directives with temporal adjudication."""

    new_memory_id: str = Field(..., description="ID of superseding newer directive")
    outdated_memory_id: str = Field(..., description="ID of superseded outdated directive")
    topic_keyword: str = Field(..., description="Domain or topic where contradiction arose")
    confidence_score: float = Field(..., description="Confidence score of contradiction detection")
    reason: str = Field(..., description="Detailed explanation of the contradiction")


class ScanCurateRequest(BaseModel):
    """Request payload to scan memory directives for antithetical contradictions."""

    memories: list[TombstoneCandidateDTO] = Field(
        ..., min_length=1, description="List of candidate memories to curate"
    )
    auto_tombstone: bool = Field(
        default=True,
        description="Whether to immediately transition outdated directives to tombstoned state",
    )


class ScanCurateResponse(BaseModel):
    """Report detailing detected contradictions and tombstone transitions."""

    total_scanned: int = Field(..., description="Total memories scanned")
    total_contradictions_found: int = Field(..., description="Number of contradiction pairs found")
    total_tombstoned: int = Field(..., description="Count of memories masked with tombstones")
    total_evicted: int = Field(..., description="Count of evicted memories")
    contradictions: list[ContradictionPairDTO] = Field(
        default_factory=list, description="Contradiction pairs"
    )
    timestamp: float = Field(..., description="Execution timestamp")


class FilterActiveRequest(BaseModel):
    """Request payload to screen a list of memories against active tombstone barriers."""

    candidates: list[TombstoneCandidateDTO] = Field(
        ..., description="Raw recalled memories to filter"
    )


class FilterActiveResponse(BaseModel):
    """Filtered active memories guaranteed free of tombstoned contradictions."""

    total_active: int = Field(..., description="Count of active memories passing barrier")
    active_memories: list[TombstoneCandidateDTO] = Field(
        default_factory=list, description="Screened memories"
    )


class ReviveTombstoneRequest(BaseModel):
    """Request payload to revive a tombstoned directive back to active status."""

    memory_id: str = Field(..., description="Target memory ID to revive")


class ReviveTombstoneResponse(BaseModel):
    """Result of reviving a tombstoned memory item."""

    success: bool = Field(..., description="Whether revival succeeded")
    memory_id: str = Field(..., description="Target memory ID")
    message: str = Field(..., description="Human-readable result status")


class EvictTombstonesRequest(BaseModel):
    """Request payload to physically evict tombstoned entries."""

    memory_ids: list[str] | None = Field(
        default=None, description="Specific IDs to evict, or null to evict all tombstoned entries"
    )


class EvictTombstonesResponse(BaseModel):
    """Result of memory eviction operation."""

    evicted_count: int = Field(..., description="Number of entries physically evicted")
    message: str = Field(..., description="Human-readable status summary")


class TombstoneRecordDTO(BaseModel):
    """Audit entry recording the lifecycle of a curated memory directive."""

    memory_id: str = Field(..., description="Memory identifier")
    state: str = Field(..., description="Lifecycle state (active, tombstoned, evicted, revived)")
    tombstoned_at: float | None = Field(default=None, description="Timestamp of tombstone application")
    superseded_by_id: str | None = Field(default=None, description="ID of superseding directive")
    reason: str | None = Field(default=None, description="Contradiction reason")
    evicted_at: float | None = Field(default=None, description="Timestamp of eviction")


class ListRecordsResponse(BaseModel):
    """Collection of tombstone audit records for UI curation panel."""

    total_records: int = Field(..., description="Total records count")
    records: list[TombstoneRecordDTO] = Field(default_factory=list, description="Audit records")
