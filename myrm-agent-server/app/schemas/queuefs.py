"""[POS]: app/schemas/queuefs.py
[INPUT]: Async DAG pipeline stages, task tracking, and hierarchical path lock parameters.
[OUTPUT]: Strongly typed Pydantic models for QueueFS background task scheduling and lock management.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class SemanticDAGStageAPI(StrEnum):
    """Discrete sequential stages in the QueueFS semantic processing DAG."""

    INGESTION = "ingestion"
    CHUNKING = "chunking"
    SIDECAR = "sidecar"
    EMBEDDING = "embedding"
    INDEXING = "indexing"


class SemanticTaskStatusAPI(StrEnum):
    """Lifecycle status of a QueueFS semantic processing DAG task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SemanticLockModeAPI(StrEnum):
    """Lock mode for hierarchical semantic path resources."""

    EXCLUSIVE = "exclusive"
    SHARED = "shared"


class QueueFSTaskSubmitRequest(BaseModel):
    """Payload to submit a resource to the asynchronous QueueFS pipeline."""

    resource_uri: str = Field(..., description="Canonical URI or context path (e.g. context://resources/doc.md)")
    payload: str = Field(default="", description="Raw text payload to process through the DAG")
    stages: list[SemanticDAGStageAPI] | None = Field(
        default=None,
        description="Optional custom pipeline stages override",
    )


class QueueFSTaskResponse(BaseModel):
    """State, progress, and execution stage details of a QueueFS task."""

    task_id: str = Field(..., description="Unique task identifier")
    resource_uri: str = Field(..., description="Canonical resource URI")
    payload: str = Field(default="", description="Raw text payload")
    stages: list[SemanticDAGStageAPI] = Field(default_factory=list, description="Stages in pipeline")
    current_stage: SemanticDAGStageAPI = Field(..., description="Active or last reached stage")
    status: SemanticTaskStatusAPI = Field(..., description="Current task lifecycle status")
    progress_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Execution progress percentage")
    created_at_epoch: float = Field(..., description="Submission timestamp epoch")
    updated_at_epoch: float = Field(..., description="Last state transition timestamp epoch")
    error_message: str | None = Field(default=None, description="Diagnostic error if failed")


class QueueFSStatsResponse(BaseModel):
    """Aggregated queue and lock telemetry statistics."""

    pending_tasks: int = Field(default=0, ge=0, description="Count of pending tasks")
    running_tasks: int = Field(default=0, ge=0, description="Count of currently running tasks")
    completed_tasks: int = Field(default=0, ge=0, description="Count of completed tasks")
    failed_tasks: int = Field(default=0, ge=0, description="Count of failed tasks")
    active_locks: int = Field(default=0, ge=0, description="Total active path leases in memory")


class AcquireLockRequest(BaseModel):
    """Payload to acquire a fine-grained hierarchical path lock lease."""

    path_pattern: str = Field(..., description="Target path or glob pattern (e.g. context://resources/*)")
    owner: str = Field(..., description="Identifier of the acquiring worker or session")
    mode: SemanticLockModeAPI = Field(
        default=SemanticLockModeAPI.EXCLUSIVE,
        description="Lock mode (exclusive or shared)",
    )
    ttl_seconds: float | None = Field(default=None, gt=0.0, description="Lease time-to-live in seconds")


class AcquireLockResponse(BaseModel):
    """Result of lock acquisition attempt."""

    lock_id: str = Field(..., description="Unique lease identifier")
    path_pattern: str = Field(..., description="Locked path pattern")
    mode: SemanticLockModeAPI = Field(..., description="Granted lock mode")
    owner: str = Field(..., description="Lease owner")
    expires_at_epoch: float = Field(..., description="Lease expiration epoch timestamp")


class ReleaseLockRequest(BaseModel):
    """Payload to voluntarily release an active lock lease."""

    lock_id: str = Field(..., description="Lease identifier to release")
    owner: str = Field(..., description="Owner identity verification")


class ReleaseLockResponse(BaseModel):
    """Result of release operation."""

    released: bool = Field(..., description="Whether the lock was found and released")


class CheckLockResponse(BaseModel):
    """Telemetry regarding path locking status and active leases count."""

    path: str = Field(..., description="Target path checked")
    is_locked: bool = Field(..., description="Whether path is currently under an active lease")
    active_locks_count: int = Field(..., description="Total count of active leases in memory")
