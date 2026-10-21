"""
[INPUT]: Model invocation metadata, auxiliary call statuses, and token usage reports.
[OUTPUT]: REST API endpoints for canonical usage ledger preventing pseudo-free zero-token representation on aborted calls.
[POS]: myrm-agent/myrm-agent-server/app/api/system/aborted_usage_ledger_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.aborted_usage_ledger import (
    AbortedUsageUnknownStats,
    AuxiliaryCallKind,
    CanonicalUsageLedgerManager,
    CanonicalUsageLedgerRow,
    LedgerCallStatus,
    UsageAvailabilityKind,
)

router = APIRouter(prefix="/aborted-usage-ledger", tags=["aborted-usage-ledger"])

_default_manager = CanonicalUsageLedgerManager()


def get_default_ledger_manager() -> CanonicalUsageLedgerManager:
    return _default_manager


# --- Request Models ---


class RecordLedgerCallRequest(BaseModel):
    session_id: str = Field(...)
    task_id: str = Field(...)
    call_kind: str = Field(default="primary", description="primary | auxiliary_summary | auxiliary_audit | auxiliary_router | auxiliary_compaction | auxiliary_other")
    call_status: str = Field(default="completed", description="completed | aborted | failed | cancelled")
    prompt_tokens: Optional[int] = Field(default=None, ge=0)
    completion_tokens: Optional[int] = Field(default=None, ge=0)
    total_tokens: Optional[int] = Field(default=None, ge=0)
    cost_usd: Optional[float] = Field(default=None, ge=0.0)
    provider_raw_status: str = Field(default="")
    timestamp_ms: Optional[int] = Field(default=None)


# --- Endpoints ---


@router.post("/record", response_model=CanonicalUsageLedgerRow)
def record_ledger_call(req: RecordLedgerCallRequest) -> CanonicalUsageLedgerRow:
    """Record a model invocation into the canonical ledger, enforcing usage-unknown on aborted calls without token report."""
    try:
        kind_enum = AuxiliaryCallKind(req.call_kind.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid call_kind '{req.call_kind}'. Valid options: {[k.value for k in AuxiliaryCallKind]}",
        )

    try:
        status_enum = LedgerCallStatus(req.call_status.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid call_status '{req.call_status}'. Valid options: {[s.value for s in LedgerCallStatus]}",
        )

    manager = get_default_ledger_manager()
    return manager.record_call(
        session_id=req.session_id,
        task_id=req.task_id,
        call_kind=kind_enum,
        call_status=status_enum,
        prompt_tokens=req.prompt_tokens,
        completion_tokens=req.completion_tokens,
        total_tokens=req.total_tokens,
        cost_usd=req.cost_usd,
        provider_raw_status=req.provider_raw_status,
        timestamp_ms=req.timestamp_ms,
    )


@router.get("/summary", response_model=AbortedUsageUnknownStats)
def get_ledger_summary(session_id: Optional[str] = Query(default=None)) -> AbortedUsageUnknownStats:
    """Retrieve aggregated stats isolating known token/cost consumption from unknown aborted calls."""
    manager = get_default_ledger_manager()
    return manager.get_stats(session_id=session_id)


@router.get("/records", response_model=List[CanonicalUsageLedgerRow])
def get_ledger_records(
    session_id: Optional[str] = Query(default=None),
    call_kind: Optional[str] = Query(default=None),
    usage_availability: Optional[str] = Query(default=None),
    call_status: Optional[str] = Query(default=None),
) -> List[CanonicalUsageLedgerRow]:
    """Retrieve canonical ledger rows with optional filtering."""
    kind_enum: Optional[AuxiliaryCallKind] = None
    if call_kind:
        try:
            kind_enum = AuxiliaryCallKind(call_kind.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid call_kind '{call_kind}'")

    availability_enum: Optional[UsageAvailabilityKind] = None
    if usage_availability:
        try:
            availability_enum = UsageAvailabilityKind(usage_availability.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid usage_availability '{usage_availability}'")

    status_enum: Optional[LedgerCallStatus] = None
    if call_status:
        try:
            status_enum = LedgerCallStatus(call_status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid call_status '{call_status}'")

    manager = get_default_ledger_manager()
    return manager.get_rows(
        session_id=session_id,
        call_kind=kind_enum,
        usage_availability=availability_enum,
        call_status=status_enum,
    )


@router.post("/reset")
def reset_ledger() -> Dict[str, str]:
    """Reset canonical ledger rows for isolated testing."""
    manager = get_default_ledger_manager()
    manager.reset()
    return {"status": "reset_completed"}
