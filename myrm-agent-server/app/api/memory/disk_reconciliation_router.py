"""[POS]: app/api/memory/disk_reconciliation_router.py
[INPUT]: FastAPI APIRouter, Depends, HTTPException, Query, and disk reconciliation schemas.
[OUTPUT]: API router exposing endpoints for disk memory synchronization, write gate policy inspection/updates, and FTS search.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.disk_reconciliation import (
    FtsReconciledHitDTO,
    ReconciliationReportDTO,
    ReconciliationStatsDTO,
    SetWriteGatePolicyRequestDTO,
    TriggerReconciliationRequestDTO,
    WriteGateCheckResultDTO,
)
from app.services.memory.disk_reconciliation_service import (
    DiskReconciliationService,
    get_disk_reconciliation_service,
)

router = APIRouter(prefix="/reconciliation", tags=["memory-reconciliation"])


@router.post("/sync", response_model=ReconciliationReportDTO)
async def trigger_reconciliation(
    request: TriggerReconciliationRequestDTO,
    service: DiskReconciliationService = Depends(get_disk_reconciliation_service),
) -> ReconciliationReportDTO:
    """Executes a bi-directional reconciliation pass over disk Markdown directories."""
    return service.trigger_reconciliation(request)


@router.get("/write-gate", response_model=WriteGateCheckResultDTO)
async def check_write_gate(
    session_id: str | None = Query(default=None, description="Optional target session ID to check"),
    service: DiskReconciliationService = Depends(get_disk_reconciliation_service),
) -> WriteGateCheckResultDTO:
    """Evaluates whether persistent memory writes are allowed under active gate policy."""
    return service.check_write_gate(session_id=session_id)


@router.post("/write-gate", response_model=WriteGateCheckResultDTO)
async def set_write_gate_policy(
    request: SetWriteGatePolicyRequestDTO,
    service: DiskReconciliationService = Depends(get_disk_reconciliation_service),
) -> WriteGateCheckResultDTO:
    """Updates the memory write gate policy globally or for a specific session."""
    try:
        return service.set_write_gate_policy(request)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get("/search", response_model=list[FtsReconciledHitDTO])
async def search(
    query: str = Query(..., min_length=1, description="Keyword search term"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
    service: DiskReconciliationService = Depends(get_disk_reconciliation_service),
) -> list[FtsReconciledHitDTO]:
    """Executes full-text ranked query across reconciled memory notes."""
    return service.search(query=query, limit=limit)


@router.get("/stats", response_model=ReconciliationStatsDTO)
async def get_stats(
    service: DiskReconciliationService = Depends(get_disk_reconciliation_service),
) -> ReconciliationStatsDTO:
    """Returns summary metrics on indexed disk memory notes and active write gate policy."""
    return service.get_stats()
