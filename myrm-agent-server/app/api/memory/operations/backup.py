"""Memory backup and restore endpoints.

Provides API endpoints for creating, listing, restoring, and deleting memory backups.
Uses VolumeBackupStrategy for sandbox persistent storage.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_memory_manager
from app.schemas.memory.crud import (
    BackupMetadataResponse,
    CreateBackupRequest,
    CreateBackupResponse,
    ListBackupsResponse,
    RestoreBackupRequest,
    RestoreBackupResponse,
)
from app.services.memory.backup import VolumeBackupStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup")


@router.post("/create", response_model=CreateBackupResponse)
async def create_backup(
    request: CreateBackupRequest,
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> CreateBackupResponse:
    """Create a complete memory backup.

    Backs up all memories (semantic, episodic, conversation) and
    relational data (profiles, rules) to sandbox persistent volume.

    Returns:
        Backup creation result with metadata
    """
    try:
        strategy = VolumeBackupStrategy()
        result = await memory_manager.create_backup(
            strategy=strategy,
            description=request.description,
        )

        if result.success and result.metadata:
            return CreateBackupResponse(
                success=True,
                backup_id=result.metadata.backup_id,
                duration_ms=result.duration_ms,
                error=None,
                metadata=BackupMetadataResponse(
                    backup_id=result.metadata.backup_id,
                    created_at=result.metadata.created_at,
                    memory_count=result.metadata.memory_count,
                    size_bytes=result.metadata.size_bytes,
                    collections=result.metadata.collections,
                    description=result.metadata.description,
                ),
            )
        else:
            return CreateBackupResponse(
                success=False,
                backup_id=None,
                duration_ms=result.duration_ms,
                error=result.error or "Unknown error",
                metadata=None,
            )
    except Exception as e:
        logger.exception("Backup creation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup creation failed: {e!s}",
        ) from e


@router.get("/list", response_model=ListBackupsResponse)
async def list_backups(
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> ListBackupsResponse:
    """List all backups for the current user.

    Returns:
        List of backup metadata sorted by creation date (newest first)
    """
    try:
        strategy = VolumeBackupStrategy()
        backups = await memory_manager.list_backups(strategy=strategy)

        return ListBackupsResponse(
            backups=[
                BackupMetadataResponse(
                    backup_id=b.backup_id,
                    created_at=b.created_at,
                    memory_count=b.memory_count,
                    size_bytes=b.size_bytes,
                    collections=b.collections,
                    description=b.description,
                )
                for b in backups
            ],
            total=len(backups),
        )
    except Exception as e:
        logger.exception("Failed to list backups: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list backups: {e!s}",
        ) from e


@router.post("/restore", response_model=RestoreBackupResponse)
async def restore_backup(
    request: RestoreBackupRequest,
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> RestoreBackupResponse:
    """Restore memories from a backup.

    Args:
        request: Restore request with backup_id and overwrite flag

    Returns:
        Restore operation result
    """
    try:
        strategy = VolumeBackupStrategy()
        result = await memory_manager.restore_backup(
            backup_id=request.backup_id,
            strategy=strategy,
            overwrite=request.overwrite,
        )

        return RestoreBackupResponse(
            success=result.success,
            restored_count=result.restored_count,
            duration_ms=result.duration_ms,
            error=result.error,
        )
    except Exception as e:
        logger.exception("Backup restoration failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup restoration failed: {e!s}",
        ) from e


@router.delete("/{backup_id}", response_model=dict[str, bool])
async def delete_backup(
    backup_id: str,
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> dict[str, bool]:
    """Delete a backup.

    Args:
        backup_id: Backup identifier to delete

    Returns:
        Success status
    """
    try:
        strategy = VolumeBackupStrategy()
        success = await memory_manager.delete_backup(
            backup_id=backup_id,
            strategy=strategy,
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup not found: {backup_id}",
            )

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Backup deletion failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup deletion failed: {e!s}",
        ) from e
