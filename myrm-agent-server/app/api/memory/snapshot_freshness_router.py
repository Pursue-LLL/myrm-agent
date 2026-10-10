"""FastAPI router for Snapshot Lag Aware Memory Freshness and Disk Verification Suite (Item 157).

[INPUT]
- Session snapshot initialization, write delta recording, state lookups, and hint generations.

[OUTPUT]
- MemorySnapshotDigestDTO, SnapshotFreshnessStateDTO, DirectDiskReadHintDTO, DeltaPatchBlockDTO.

[POS]
- FastAPI router endpoints for Item 157 SnapshotLagAwareMemoryFreshnessAndDiskVerificationContractSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.snapshot_freshness import (
    DeltaPatchBlockDTO,
    DirectDiskReadHintDTO,
    InitSnapshotRequest,
    MemorySnapshotDigestDTO,
    RecordWriteRequest,
    SnapshotFreshnessStateDTO,
)
from app.services.memory.snapshot_freshness_service import SnapshotFreshnessService

router = APIRouter(prefix="/snapshot-freshness", tags=["memory-snapshot-freshness"])
_service = SnapshotFreshnessService()


def get_snapshot_freshness_service() -> SnapshotFreshnessService:
    """Dependency helper providing the active SnapshotFreshnessService."""
    return _service


@router.post(
    "/init",
    response_model=MemorySnapshotDigestDTO,
    status_code=status.HTTP_201_CREATED,
)
async def init_session_snapshot(
    req: InitSnapshotRequest,
) -> MemorySnapshotDigestDTO:
    """Initialize and seal the memory snapshot generation digest for an active session."""
    return get_snapshot_freshness_service().init_session_snapshot(req)


@router.post(
    "/record-write",
    response_model=SnapshotFreshnessStateDTO,
)
async def record_write(
    req: RecordWriteRequest,
) -> SnapshotFreshnessStateDTO:
    """Record an ongoing memory write event to persistent storage and mark snapshot as dirty."""
    return get_snapshot_freshness_service().record_write(req)


@router.get(
    "/status/{session_id}",
    response_model=SnapshotFreshnessStateDTO,
)
async def get_freshness_state(
    session_id: str,
) -> SnapshotFreshnessStateDTO:
    """Fetch current staleness and dirty state of a session."""
    return get_snapshot_freshness_service().get_state(session_id)


@router.get(
    "/hint/{session_id}",
    response_model=DirectDiskReadHintDTO,
)
async def get_disk_read_hint(
    session_id: str,
) -> DirectDiskReadHintDTO:
    """Generate a direct-disk verification contract hint for dirty memory contexts."""
    return get_snapshot_freshness_service().generate_disk_read_hint(session_id)


@router.get(
    "/delta-patch/{session_id}",
    response_model=DeltaPatchBlockDTO,
)
async def get_delta_patch(
    session_id: str,
) -> DeltaPatchBlockDTO:
    """Render intra-session memory delta patch block for append-only prompt injection."""
    return get_snapshot_freshness_service().render_delta_patch(session_id)


@router.post(
    "/reset/{session_id}",
    response_model=dict[str, str],
)
async def reset_session(
    session_id: str,
) -> dict[str, str]:
    """Reset tracking state for a completed session."""
    get_snapshot_freshness_service().reset_session(session_id)
    return {"status": "ok", "session_id": session_id}
