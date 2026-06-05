"""Checkpoint and file snapshot management REST API.

Provides endpoints for:
- Subagent checkpoint management (list, resume, delete, cleanup)
- File snapshot management (list, restore, diff, delete, cleanup)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.agent.file_snapshot.local_store import LocalFileSnapshotStore
from myrm_agent_harness.agent.sub_agents.checkpoint.saver import SubagentCheckpointStorage
from pydantic import BaseModel, Field

router = APIRouter(prefix="/checkpoint", tags=["checkpoint"])

# Global instances
_checkpoint_storage = SubagentCheckpointStorage()
_file_snapshot_store = LocalFileSnapshotStore()


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


@router.get("/list", response_model=CheckpointListResponse)
async def list_checkpoints(
    session_id: str | None = Query(None, description="Filter by session ID"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of checkpoints to return"),
) -> CheckpointListResponse:
    """List all saved checkpoints.

    Args:
        session_id: Optional session ID filter
        limit: Maximum number of checkpoints to return (1-100)

    Returns:
        List of checkpoints with metadata
    """
    try:
        checkpoints = await _checkpoint_storage.list_checkpoints(session_id=session_id)

        # Apply limit
        checkpoints = checkpoints[:limit]

        # Convert to response model
        checkpoint_infos = [
            CheckpointInfo(
                task_id=cp.task_id,
                agent_type=cp.agent_type,
                session_id=cp.session_id,
                timestamp=cp.timestamp,
                progress=cp.progress,
                last_tool=cp.last_tool,
                resumable=cp.resumable,
            )
            for cp in checkpoints
        ]

        return CheckpointListResponse(
            checkpoints=checkpoint_infos,
            total=len(checkpoint_infos),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list checkpoints: {e}") from e


@router.post("/resume", response_model=CheckpointResumeResponse)
async def resume_from_checkpoint(request: CheckpointResumeRequest) -> CheckpointResumeResponse:
    """Resume execution from saved checkpoint.

    This endpoint loads the checkpoint and returns its data (messages/context) to the client.
    The client can then use this data to restart the agent conversation with preserved history.

    Args:
        request: Resume request with task_id

    Returns:
        Resume status with checkpoint data

    Note:
        This returns the checkpoint data for client-side restoration.
        For direct agent resumption, integrate with SubagentManager in agent execution layer.
    """
    try:
        checkpoint = await _checkpoint_storage.load(request.task_id)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {request.task_id}")

        if not checkpoint.resumable:
            raise HTTPException(status_code=400, detail=f"Checkpoint {request.task_id} is not resumable (missing required state)")

        checkpoint_data = {
            "messages": checkpoint.messages,
            "variables": checkpoint.variables,
            "progress": checkpoint.progress,
            "last_tool": checkpoint.last_tool,
            "timestamp": checkpoint.timestamp,
        }

        return CheckpointResumeResponse(
            status="ready",
            task_id=request.task_id,
            message=f"Checkpoint loaded successfully (agent_type={checkpoint.agent_type}, "
            f"progress={checkpoint.progress:.1%}, messages={len(checkpoint.messages)})",
            session_id=checkpoint.session_id,
            messages_count=len(checkpoint.messages),
            checkpoint_data=checkpoint_data,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resume from checkpoint: {e}") from e


@router.delete("/{task_id}")
async def delete_checkpoint(task_id: str) -> dict[str, str]:
    """Delete saved checkpoint.

    Args:
        task_id: Task ID to delete

    Returns:
        Delete status
    """
    try:
        # Check if checkpoint exists
        checkpoint = await _checkpoint_storage.load(task_id)
        if not checkpoint:
            raise HTTPException(status_code=404, detail=f"Checkpoint not found: {task_id}")

        # Delete checkpoint
        await _checkpoint_storage.delete(task_id)

        return {"status": "deleted", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete checkpoint: {e}") from e


@router.post("/cleanup")
async def cleanup_old_checkpoints(
    ttl_days: int = Query(7, ge=1, le=30, description="Time-to-live in days (1-30)"),
) -> dict[str, object]:
    """Cleanup old checkpoints (default: 7 days TTL).

    Args:
        ttl_days: Time-to-live in days (1-30)

    Returns:
        Cleanup statistics
    """
    try:
        ttl_seconds = ttl_days * 86400
        deleted = await _checkpoint_storage.cleanup_old_checkpoints(ttl_seconds=ttl_seconds)

        return {
            "status": "success",
            "deleted": deleted,
            "ttl_days": ttl_days,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup checkpoints: {e}") from e


# ============================================================================
# File Snapshot Endpoints
# ============================================================================


class FileSnapshotInfoResponse(BaseModel):
    """File snapshot information response model."""

    snapshot_id: str
    working_dir: str
    trigger: str
    created_at: float
    file_count: int
    description: str = ""


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


class FileDiffResponse(BaseModel):
    """File diff response model."""

    snapshot_id: str
    changes: list[FileChangeResponse]
    total_changes: int


@router.get("/file-snapshot/list", response_model=FileSnapshotListResponse)
async def list_file_snapshots(
    working_dir: str = Query(..., description="Working directory to list snapshots for"),
    limit: int = Query(20, ge=1, le=100, description="Maximum snapshots to return"),
) -> FileSnapshotListResponse:
    """List file snapshots for a workspace."""
    try:
        snapshots = await _file_snapshot_store.list_snapshots(working_dir, limit=limit)
        items = [
            FileSnapshotInfoResponse(
                snapshot_id=s.snapshot_id,
                working_dir=s.working_dir,
                trigger=s.trigger.value,
                created_at=s.created_at,
                file_count=s.file_count,
                description=s.description,
            )
            for s in snapshots
        ]
        return FileSnapshotListResponse(snapshots=items, total=len(items))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list file snapshots: {e}") from e


@router.post("/file-snapshot/restore", response_model=FileSnapshotRestoreResponse)
async def restore_file_snapshot(request: FileSnapshotRestoreRequest) -> FileSnapshotRestoreResponse:
    """Restore workspace to a file snapshot state.

    Automatically takes a pre-rollback snapshot before restoring.
    """
    try:
        result = await _file_snapshot_store.restore(request.snapshot_id, files=request.files)
        return FileSnapshotRestoreResponse(
            success=result.success,
            snapshot_id=result.snapshot_id,
            files_restored=result.files_restored,
            pre_rollback_snapshot_id=result.pre_rollback_snapshot_id,
            error=result.error,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore file snapshot: {e}") from e


@router.get("/file-snapshot/{snapshot_id}/diff", response_model=FileDiffResponse)
async def get_file_snapshot_diff(snapshot_id: str) -> FileDiffResponse:
    """Compare a file snapshot with current workspace state."""
    try:
        diff = await _file_snapshot_store.diff(snapshot_id)
        changes = [
            FileChangeResponse(
                path=c.path,
                change_type=c.change_type,
                old_size=c.old_size,
                new_size=c.new_size,
            )
            for c in diff.changes
        ]
        return FileDiffResponse(
            snapshot_id=diff.snapshot_id,
            changes=changes,
            total_changes=diff.total_changes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get file diff: {e}") from e


@router.delete("/file-snapshot/{snapshot_id}")
async def delete_file_snapshot(snapshot_id: str) -> dict[str, str]:
    """Delete a specific file snapshot."""
    try:
        deleted = await _file_snapshot_store.delete_snapshot(snapshot_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"File snapshot not found: {snapshot_id}")
        return {"status": "deleted", "snapshot_id": snapshot_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file snapshot: {e}") from e


@router.post("/file-snapshot/cleanup")
async def cleanup_file_snapshots(
    working_dir: str = Query(..., description="Working directory to cleanup"),
    max_snapshots: int = Query(20, ge=1, le=100, description="Maximum snapshots to keep"),
) -> dict[str, object]:
    """Cleanup old file snapshots, keeping the most recent."""
    try:
        deleted = await _file_snapshot_store.cleanup(working_dir, max_snapshots=max_snapshots)
        return {
            "status": "success",
            "deleted": deleted,
            "max_snapshots": max_snapshots,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup file snapshots: {e}") from e
