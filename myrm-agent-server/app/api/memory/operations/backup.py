"""Memory backup and restore endpoints.

Creates, lists, restores and deletes complete snapshots of the user's memories (profile,
rules, semantic, episodic) on the sandbox persistent volume. Creating and restoring need a
manager that stores directly (``get_crud_memory_manager``): restored memories must not
land in the approval queue. Listing and deleting only touch the volume.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.backup import BackupMetadata

from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.crud import (
    BackupMetadataResponse,
    CreateBackupRequest,
    CreateBackupResponse,
    ListBackupsResponse,
    RestoreBackupRequest,
    RestoreBackupResponse,
)
from app.services.memory.backup.service import MemoryBackupService
from app.services.memory.backup.snapshot import SnapshotError
from app.services.memory.backup.volume_store import BackupNotFoundError, VolumeBackupStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup")


def get_backup_store() -> VolumeBackupStore:
    return VolumeBackupStore()


def _to_response(metadata: BackupMetadata) -> BackupMetadataResponse:
    return BackupMetadataResponse(
        backup_id=metadata.backup_id,
        created_at=metadata.created_at,
        memory_count=metadata.memory_count,
        size_bytes=metadata.size_bytes,
        collections=metadata.collections,
        description=metadata.description,
    )


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


@router.post("/create", response_model=CreateBackupResponse)
async def create_backup(
    request: CreateBackupRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
    store: VolumeBackupStore = Depends(get_backup_store),
) -> CreateBackupResponse:
    """Snapshot every memory onto the persistent volume.

    Reports ``success=false`` rather than saving a backup that misses memories.
    """
    start = time.perf_counter()
    try:
        metadata = await MemoryBackupService(manager, store).create(request.description)
    except SnapshotError as exc:
        return CreateBackupResponse(success=False, duration_ms=_elapsed_ms(start), error=str(exc))
    except Exception as exc:
        logger.exception("Backup creation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Backup creation failed",
        ) from exc
    return CreateBackupResponse(
        success=True,
        backup_id=metadata.backup_id,
        duration_ms=_elapsed_ms(start),
        metadata=_to_response(metadata),
    )


@router.get("/list", response_model=ListBackupsResponse)
async def list_backups(store: VolumeBackupStore = Depends(get_backup_store)) -> ListBackupsResponse:
    """List the backups on the volume, newest first."""
    try:
        backups = await asyncio.to_thread(store.list_backups)
    except Exception as exc:
        logger.exception("Failed to list backups: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list backups",
        ) from exc
    return ListBackupsResponse(backups=[_to_response(b) for b in backups], total=len(backups))


@router.post("/restore", response_model=RestoreBackupResponse)
async def restore_backup(
    request: RestoreBackupRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
    store: VolumeBackupStore = Depends(get_backup_store),
) -> RestoreBackupResponse:
    """Restore memories from a backup.

    ``overwrite=false`` merges the backup into the current memories, skipping what is
    already there. ``overwrite=true`` first saves the current memories as a new backup,
    then replaces them with the backup's.
    """
    start = time.perf_counter()
    try:
        restored = await MemoryBackupService(manager, store).restore(request.backup_id, overwrite=request.overwrite)
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SnapshotError as exc:
        return RestoreBackupResponse(success=False, restored_count=0, duration_ms=_elapsed_ms(start), error=str(exc))
    except Exception as exc:
        logger.exception("Backup restoration failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Backup restoration failed",
        ) from exc
    return RestoreBackupResponse(success=True, restored_count=restored, duration_ms=_elapsed_ms(start))


@router.delete("/{backup_id}", response_model=dict[str, bool])
async def delete_backup(
    backup_id: str,
    store: VolumeBackupStore = Depends(get_backup_store),
) -> dict[str, bool]:
    """Delete a backup from the volume."""
    try:
        deleted = await asyncio.to_thread(store.delete, backup_id)
    except Exception as exc:
        logger.exception("Backup deletion failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Backup deletion failed",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Backup not found: {backup_id}")
    return {"success": True}
