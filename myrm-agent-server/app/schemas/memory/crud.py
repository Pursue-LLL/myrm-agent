"""Memory CRUD shared schemas.

[INPUT]
pydantic::BaseModel (POS: 请求/响应模型基类)

[OUTPUT]
MemoryItem and memory CRUD / pending / backup / status / taste / preference request-response models

[POS]
记忆 CRUD 共享 Schema。api 与 services 层共用。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """Memory item in API response"""

    id: str
    memory_type: str
    content: str
    importance: float = 0.5
    confidence: float = 1.0
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)

    projected_category: str | None = None
    projected_label: str | None = None
    influence_explanation: str | None = None

    key: str | None = None
    value: str | None = None
    trigger: str | None = None
    action: str | None = None
    reasoning: str | None = None
    application: str | None = None
    tool_name: str | None = None
    tool_rule_priority: str | None = None
    event_type: str | None = None
    related_entities: list[str] = Field(default_factory=list)
    correction_of: str | None = None
    source_error: str | None = None
    tags: list[str] = Field(default_factory=list)
    access_count: int | None = None
    last_accessed_at: datetime | None = None


class MemorySearchResponse(BaseModel):
    """Response for memory search endpoint"""

    results: list[MemoryItem]
    scores: list[float]
    query: str
    total: int


class MemoryStatsResponse(BaseModel):
    """Response for memory statistics endpoint"""

    total_memories: int
    by_type: dict[str, int]


class TasteSummaryResponse(BaseModel):
    """Aggregated user preference summary extracted from memories"""

    style_keywords: list[str] = Field(default_factory=list)
    preference_keywords: list[str] = Field(default_factory=list)
    avoid_keywords: list[str] = Field(default_factory=list)
    current_goals: list[str] = Field(default_factory=list)
    reply_style: str | None = None
    technical_depth: str | None = None
    proactivity: str | None = None
    summary: str = ""
    memory_count: int = 0


class PendingMemoryItem(BaseModel):
    """Pending memory item awaiting user approval"""

    id: str
    user_id: str
    memory_type: str
    content: str
    extra_data: dict[str, object] | None = None
    source_chat_id: str | None = None
    source_message_id: str | None = None
    status: str
    created_at: datetime
    resolved_at: datetime | None = None


class PendingMemoriesResponse(BaseModel):
    """Response for pending memories endpoint"""

    items: list[PendingMemoryItem]
    total: int


class ApproveMemoryRequest(BaseModel):
    """Request to approve a pending memory"""

    edited_content: str | None = None


class BatchMemoryRequest(BaseModel):
    """Request for batch operations"""

    memory_ids: list[str]


class BatchMemoryResponse(BaseModel):
    """Response for batch operations"""

    success_count: int
    failed_count: int
    failed_ids: list[str] = Field(default_factory=list)


class CreateMemoryRequest(BaseModel):
    """Request to create a new memory"""

    memory_type: str = Field(..., description="Memory type: profile, semantic, episodic, procedural")
    content: str = Field(..., min_length=1, max_length=2000, description="Memory content")
    importance: float = Field(0.5, ge=0.0, le=1.0, description="Importance score")
    tags: list[str] = Field(default_factory=list, description="Tags (semantic/episodic only)")

    key: str | None = Field(None, description="Attribute key (profile only)")
    value: str | None = Field(None, description="Attribute value (profile only)")
    trigger: str | None = Field(None, description="Trigger condition (procedural only)")
    action: str | None = Field(None, description="Action to take (procedural only)")
    related_entities: list[str] = Field(
        default_factory=list,
        description="Related entities (episodic only, for graph indexing)",
    )


class CorrectMemoryRequest(BaseModel):
    """Request to correct a factually wrong semantic memory."""

    corrected_content: str = Field(..., min_length=1, max_length=2000, description="Corrected content")


class UpdateMemoryRequest(BaseModel):
    """Request to update an existing memory"""

    content: str | None = Field(None, min_length=1, max_length=2000, description="New content")
    reasoning: str | None = Field(None, max_length=2000, description="New reasoning (Why)")
    application: str | None = Field(None, max_length=2000, description="New application (How)")
    importance: float | None = Field(None, ge=0.0, le=1.0, description="New importance score")
    tags: list[str] | None = Field(None, description="New tags (semantic/episodic only)")


class UpdateMemoryStatusRequest(BaseModel):
    """Request to change a memory's lifecycle status"""

    status: str = Field(..., description="New status: active, disabled, or archived")


class DeleteMemoryRequest(BaseModel):
    """Request to delete a memory"""

    memory_id: str
    memory_type: str


class PaginationInfo(BaseModel):
    """Pagination information"""

    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class MemoryListPaginatedResponse(BaseModel):
    """Paginated response for memory list endpoint"""

    items: list[MemoryItem]
    pagination: PaginationInfo


MEMORY_EXPORT_VERSION = 1


class MemoryExportResponse(BaseModel):
    """Response for memory export endpoint"""

    version: int = Field(
        MEMORY_EXPORT_VERSION,
        description="Export schema version for forward compatibility",
    )
    data: dict[str, list[dict[str, object]]]
    total_count: int


class BackupMetadataResponse(BaseModel):
    """Memory backup metadata response"""

    backup_id: str
    created_at: datetime
    memory_count: int
    size_bytes: int
    collections: list[str]
    description: str | None = None


class CreateBackupRequest(BaseModel):
    """Request to create memory backup"""

    description: str | None = Field(None, description="Optional backup description")


class CreateBackupResponse(BaseModel):
    """Response for backup creation"""

    success: bool
    backup_id: str | None = None
    duration_ms: float
    error: str | None = None
    metadata: BackupMetadataResponse | None = None


class ListBackupsResponse(BaseModel):
    """Response for listing backups"""

    backups: list[BackupMetadataResponse]
    total: int


class RestoreBackupRequest(BaseModel):
    """Request to restore memory backup"""

    backup_id: str = Field(..., description="Backup ID to restore")
    overwrite: bool = Field(False, description="Clear existing memories before restore")


class RestoreBackupResponse(BaseModel):
    """Response for backup restoration"""

    success: bool
    restored_count: int
    duration_ms: float
    error: str | None = None


class AdvancedSearchRequest(BaseModel):
    """Advanced memory search with filtering, sorting, grouping"""

    query: str | None = Field(None, description="Search query (empty for all memories)")
    memory_types: list[str] | None = Field(None, description="Filter by memory types")
    created_after: datetime | None = Field(None, description="Filter created after date")
    created_before: datetime | None = Field(None, description="Filter created before date")
    importance_min: float | None = Field(None, ge=0.0, le=1.0, description="Minimum importance")
    importance_max: float | None = Field(None, ge=0.0, le=1.0, description="Maximum importance")
    access_count_min: int | None = Field(None, ge=0, description="Minimum access count")
    sort_by: str = Field(
        "created_at",
        description="Sort field: created_at, updated_at, importance, access_count",
    )
    sort_order: str = Field("desc", description="Sort order: asc or desc")
    group_by: str | None = Field(None, description="Group by: memory_type, date_day, date_week, date_month")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Page size (1-100)")


class MemoryGroup(BaseModel):
    """Grouped memory results"""

    group_key: str
    group_label: str
    count: int
    items: list[MemoryItem]


class AdvancedSearchResponse(BaseModel):
    """Response for advanced memory search"""

    results: list[MemoryItem] | list[MemoryGroup]
    total: int
    page: int
    page_size: int
    total_pages: int
    grouped: bool


class RateMemoryRequest(BaseModel):
    """Request to rate a memory"""

    score: int = Field(..., ge=1, le=5, description="Rating score (1=bad, 5=excellent)")


class RateMemoryResponse(BaseModel):
    """Response for memory rating"""

    success: bool
    memory_id: str
    score: int


# ── Preference Stability Schemas ─────────────────────────────────────


class PreferenceFacetItem(BaseModel):
    """API response model for a single preference facet."""

    id: str
    key: str
    value: str
    category: str
    cue: str
    lifecycle: str
    stability: float
    evidence_count: int
    memory_ids: list[str] = Field(default_factory=list)
    first_seen: datetime
    last_seen: datetime
    user_pinned: bool = False
    user_forgotten: bool = False


class PreferenceFacetListResponse(BaseModel):
    """Response for preference facets list endpoint."""

    items: list[PreferenceFacetItem]
    total: int
    active_count: int
    provisional_count: int
    candidate_count: int
