"""[POS]: app/schemas/cognitive_box.py
[INPUT]: HTTP requests for cognitive memory box management and intake screening.
[OUTPUT]: Pydantic schemas for cognitive entries, evaluation reports, and snapshots.
"""

from pydantic import BaseModel, Field


class CognitiveEntryDTO(BaseModel):
    """Data transfer object for a cognitive memory item."""

    id: str
    layer: str
    content: str
    confidence: float
    tags: list[str] = Field(default_factory=list)
    created_at: float
    updated_at: float
    source_session: str | None = None


class EvaluateIntakeRequest(BaseModel):
    """Request payload to screen candidate content through the strict intake filter."""

    content: str = Field(..., min_length=1, description="Raw candidate statement or conversation chunk")
    source_session: str | None = Field(default=None, description="Optional originating session ID")
    forced_layer: str | None = Field(default=None, description="Optional target layer override")
    tags: list[str] = Field(default_factory=list, description="Optional tag annotations")


class IntakeReportResponse(BaseModel):
    """Audit report for memory admission screening."""

    decision: str
    layer: str | None = None
    confidence: float
    reason: str
    sanitized_content: str
    existing_entry_id: str | None = None
    admitted_entry: CognitiveEntryDTO | None = None


class WriteDirectEntryRequest(BaseModel):
    """Request to directly write or update a cognitive entry."""

    id: str | None = None
    layer: str
    content: str
    confidence: float = 0.95
    tags: list[str] = Field(default_factory=list)
    source_session: str | None = None


class CognitiveBoxSnapshotResponse(BaseModel):
    """Full snapshot of the cognitive memory box."""

    timestamp: float
    total_count: int
    counts_by_layer: dict[str, int]
    entries: list[CognitiveEntryDTO]


class ClearLayerResponse(BaseModel):
    """Response after purging a cognitive layer."""

    layer: str
    purged_count: int
