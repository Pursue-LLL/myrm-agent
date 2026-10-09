"""REST API router for Durable Revision & Concurrent Writes.

[POS]
Provides HTTP endpoints for durable memory writes, point-in-time MVCC snapshot reads,
authoritative change receipts retrieval, and forward rollback safety.

[INPUT]
- fastapi
- app.schemas.durable_revision
- app.services.memory.durable_revision.provider

[OUTPUT]
- router (FastAPI APIRouter)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.durable_revision import (
    ChangeReceiptDTO,
    DurableRevisionStatsDTO,
    RetractRequestDTO,
    RollbackRequestDTO,
    SnapshotReadViewDTO,
    WritePayloadDTO,
)
from app.services.memory.durable_revision.provider import (
    execute_durable_write,
    execute_retract,
    execute_rollback,
    get_revision_stats,
    query_receipt,
    query_snapshot,
)

router = APIRouter(prefix="/durable-revision", tags=["Durable Revision & Concurrent Writes"])


@router.post(
    "/write",
    response_model=ChangeReceiptDTO,
    status_code=status.HTTP_200_OK,
    summary="Execute durable atomic memory write",
)
def write_memory_mutation(req: WritePayloadDTO) -> ChangeReceiptDTO:
    """Commit a memory mutation with fine-grained lock coordination and WAL logging."""
    return execute_durable_write(req)


@router.get(
    "/snapshot/{key:path}",
    response_model=SnapshotReadViewDTO,
    status_code=status.HTTP_200_OK,
    summary="Lockless point-in-time snapshot read",
)
def get_memory_snapshot(
    key: str,
    revision: int | None = Query(default=None, ge=1, description="Specific historical revision number"),
) -> SnapshotReadViewDTO:
    """Retrieve an immutable snapshot view at the current canonical or requested historical revision."""
    snap = query_snapshot(key=key, revision=revision)
    if snap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot not found for key '{key}' (revision={revision})",
        )
    return snap


@router.get(
    "/receipt/{receipt_id}",
    response_model=ChangeReceiptDTO,
    status_code=status.HTTP_200_OK,
    summary="Query authoritative change receipt",
)
def get_change_receipt(receipt_id: str) -> ChangeReceiptDTO:
    """Retrieve an authoritative typed change receipt by its UUID."""
    rc = query_receipt(receipt_id=receipt_id)
    if rc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Change receipt '{receipt_id}' not found",
        )
    return rc


@router.post(
    "/rollback",
    response_model=ChangeReceiptDTO,
    status_code=status.HTTP_200_OK,
    summary="Safely rollback key to prior historical revision",
)
def rollback_memory_revision(req: RollbackRequestDTO) -> ChangeReceiptDTO:
    """Revert a memory document state to target revision by publishing a forward monotonic revision."""
    return execute_rollback(req)


@router.post(
    "/retract",
    response_model=ChangeReceiptDTO,
    status_code=status.HTTP_200_OK,
    summary="Publish a tombstone retraction revision",
)
def retract_memory_key(req: RetractRequestDTO) -> ChangeReceiptDTO:
    """Publish a tombstone revision to mark key as retracted while preserving historical audit trail."""
    return execute_retract(req)


@router.get(
    "/stats",
    response_model=DurableRevisionStatsDTO,
    status_code=status.HTTP_200_OK,
    summary="Query durable revision operational statistics",
)
def get_durable_stats() -> DurableRevisionStatsDTO:
    """Retrieve real-time operational metrics across change receipts, locks, and MVCC revisions."""
    return get_revision_stats()
