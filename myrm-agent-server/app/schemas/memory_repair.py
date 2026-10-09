"""[POS]: app/schemas/memory_repair.py
[INPUT]: Request and response payload parameters for memory integrity repair and pruning APIs.
[OUTPUT]: Strongly typed Pydantic models for diagnostics, healing, stale pruning, and health metrics.
"""

from pydantic import BaseModel, Field


class IntegrityCheckResponse(BaseModel):
    """Response containing diagnostic integrity inspection results."""

    db_status: str = Field(..., description="Integrity status (healthy, degraded, corrupted, repaired)")
    fts_healthy: bool = Field(..., description="Whether FTS index tables are healthy")
    issues: list[str] = Field(default_factory=list, description="Diagnostic anomaly findings")
    checked_at_epoch: float = Field(..., description="Epoch timestamp of inspection")
    table_counts: dict[str, int] = Field(default_factory=dict, description="Row count per table")


class RepairDatabaseRequest(BaseModel):
    """Request payload to initiate automated database self-healing."""

    force_rebuild: bool = Field(default=False, description="Whether to force index and FTS rebuilding")


class RepairDatabaseResponse(BaseModel):
    """Response payload detailing automated repair actions and outcome."""

    status: str = Field(..., description="Repair execution status (success, partial, skipped, failed)")
    repaired_items: list[str] = Field(default_factory=list, description="List of successful repair operations")
    error_details: list[str] = Field(default_factory=list, description="Errors encountered during repair")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")


class PruneStaleRequest(BaseModel):
    """Request payload configuring adaptive stale memory pruning."""

    stale_days_threshold: int = Field(default=30, ge=1, description="Days without recall before marking stale")
    min_recall_count: int = Field(default=0, ge=0, description="Minimum recall count threshold")
    decay_rate: float = Field(default=0.05, gt=0.0, description="Exponential decay rate lambda")
    protect_pinned: bool = Field(default=True, description="Guard pinned entries from pruning")
    dry_run: bool = Field(default=False, description="Simulate pruning without modifying database")
    table_name: str = Field(default="myrm_memories", description="Target memory database table")
    session_id: str | None = Field(default=None, description="Optional active session id for cache preservation")


class PruneStaleResponse(BaseModel):
    """Response payload summarizing the outcome of stale entry pruning."""

    evaluated_count: int = Field(..., description="Total candidate items evaluated")
    archived_count: int = Field(..., description="Number of items archived")
    protected_count: int = Field(..., description="Number of active or pinned items protected")
    archived_ids: list[str] = Field(default_factory=list, description="Identifiers of newly archived memories")
    duration_ms: float = Field(..., description="Execution duration in milliseconds")


class MemoryHealthResponse(BaseModel):
    """Response payload presenting memory storage health metrics and score."""

    overall_health_score: float = Field(..., ge=0.0, le=100.0, description="Overall health score from 0 to 100")
    total_entries: int = Field(..., description="Total memory items stored")
    active_entries: int = Field(..., description="Active working memory entries")
    stale_entries: int = Field(..., description="Stale candidate memory entries")
    integrity_status: str = Field(..., description="Database structural integrity status")
