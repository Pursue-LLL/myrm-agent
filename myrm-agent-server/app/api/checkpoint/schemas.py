"""Pydantic schemas for checkpoint and file snapshot API endpoints.

[POS] app/api/checkpoint/schemas.py
[INPUT] None
[OUTPUT] CheckpointInfo, CheckpointListResponse, CheckpointResumeRequest,
         CheckpointResumeResponse, FileSnapshotInfoResponse, FileSnapshotListResponse,
         FileSnapshotRestoreRequest, FileSnapshotRestoreResponse,
         FileChangeResponse, FileDiffResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ============================================================================
# Subagent Checkpoint Schemas
# ============================================================================


class CheckpointInfo(BaseModel):
    """Checkpoint information response model."""

    task_id: str
    agent_type: str
    session_id: str
    timestamp: float
    progress: float
    last_tool: str | None
    resumable: bool


class CheckpointListResponse(BaseModel):
    """List checkpoints response model."""

    checkpoints: list[CheckpointInfo]
    total: int


class CheckpointResumeRequest(BaseModel):
    """Resume from checkpoint request model."""

    task_id: str = Field(..., description="Task ID to resume from checkpoint")


class CheckpointResumeResponse(BaseModel):
    """Resume from checkpoint response model."""

    status: str
    task_id: str
    message: str
    session_id: str | None = None
    messages_count: int = 0
    checkpoint_data: dict[str, object] | None = None


# ============================================================================
# File Snapshot Schemas
# ============================================================================


class FileSnapshotInfoResponse(BaseModel):
    """File snapshot information response model."""

    snapshot_id: str
    working_dir: str
    trigger: str
    created_at: float
    file_count: int
    description: str = ""
    external_effects: list[str] = Field(default_factory=list)
    agent_id: str | None = None


class FileSnapshotListResponse(BaseModel):
    """List file snapshots response model."""

    snapshots: list[FileSnapshotInfoResponse]
    total: int


class FileSnapshotRestoreRequest(BaseModel):
    """Restore file snapshot request model."""

    snapshot_id: str = Field(..., description="Snapshot ID to restore")
    files: list[str] | None = Field(None, description="Specific files to restore (null = all)")


class FileSnapshotRestoreResponse(BaseModel):
    """Restore file snapshot response model."""

    success: bool
    snapshot_id: str
    files_restored: int
    pre_rollback_snapshot_id: str | None = None
    error: str | None = None


class FileChangeResponse(BaseModel):
    """File change in a diff."""

    path: str
    change_type: str
    old_size: int | None = None
    new_size: int | None = None
    lines_added: int | None = None
    lines_deleted: int | None = None


class FileDiffResponse(BaseModel):
    """File diff response model."""

    snapshot_id: str
    changes: list[FileChangeResponse]
    total_changes: int
