"""
[INPUT]: Spend amounts, categories, message/session IDs, and branch statuses.
[OUTPUT]: REST API endpoints for durable budget ledger, restart spend recovery, and session actual-billed reconciliation.
[POS]: myrm-agent/myrm-agent-server/app/api/system/durable_budget_ledger_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.durable_budget_ledger import (
    DurableBudgetLedgerManager,
    DurableBudgetRecoverySummary,
    DurableSpendLedgerRecord,
    SessionActualBilledStatement,
    SpendCategory,
)

router = APIRouter(prefix="/durable-budget-ledger", tags=["durable-budget-ledger"])

_default_manager = DurableBudgetLedgerManager()


def get_default_budget_ledger_manager() -> DurableBudgetLedgerManager:
    return _default_manager


# --- Request Models ---


class RecordSpendRequest(BaseModel):
    cost_usd: float = Field(..., ge=0.0)
    category: str = Field(default="chat", description="chat | auxiliary | cache_warm | subagent | system")
    session_id: Optional[str] = Field(default=None)
    task_id: Optional[str] = Field(default=None)
    is_active_branch: bool = Field(default=True)
    message_id: Optional[str] = Field(default=None)
    date_utc: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    timestamp_ms: Optional[int] = Field(default=None)


class MarkDiscardedRequest(BaseModel):
    message_id: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None)


# --- Endpoints ---


@router.post("/record-spend", response_model=DurableSpendLedgerRecord)
def record_spend(req: RecordSpendRequest) -> DurableSpendLedgerRecord:
    """Record a spend entry in the durable ledger, persisting across branch discards and message deletions."""
    try:
        cat_enum = SpendCategory(req.category.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{req.category}'. Valid options: {[c.value for c in SpendCategory]}",
        )

    manager = get_default_budget_ledger_manager()
    return manager.record_spend(
        cost_usd=req.cost_usd,
        category=cat_enum,
        session_id=req.session_id,
        task_id=req.task_id,
        is_active_branch=req.is_active_branch,
        message_id=req.message_id,
        date_utc=req.date_utc,
        timestamp_ms=req.timestamp_ms,
    )


@router.post("/mark-discarded")
def mark_discarded(req: MarkDiscardedRequest) -> Dict[str, int]:
    """Mark branch spend as discarded on message retry/rewind while preserving true provider billing."""
    manager = get_default_budget_ledger_manager()
    updated = manager.mark_branch_discarded(
        message_id=req.message_id,
        session_id=req.session_id,
    )
    return {"updated_count": updated}


@router.get("/today-spent")
def get_today_spent(date_utc: Optional[str] = Query(default=None)) -> Dict[str, float]:
    """Recover accurate today's spend from durable ledger across process restarts."""
    manager = get_default_budget_ledger_manager()
    spent = manager.get_today_spent(date_utc=date_utc)
    return {"today_spent_usd": spent}


@router.get("/recovery-summary", response_model=DurableBudgetRecoverySummary)
def get_recovery_summary(
    date_utc: Optional[str] = Query(default=None),
    surviving_message_cost_usd: float = Query(default=0.0, ge=0.0),
) -> DurableBudgetRecoverySummary:
    """Retrieve recovery summary identifying underestimation gap between durable ledger and surviving messages."""
    manager = get_default_budget_ledger_manager()
    return manager.get_recovery_summary(
        date_utc=date_utc,
        surviving_message_cost_usd=surviving_message_cost_usd,
    )


@router.get("/session-billed/{session_id}", response_model=SessionActualBilledStatement)
def get_session_billed(session_id: str) -> SessionActualBilledStatement:
    """Reconcile session spend: visible branch vs actual billed total."""
    manager = get_default_budget_ledger_manager()
    return manager.get_session_actual_billed(session_id=session_id)


@router.post("/reset")
def reset_ledger() -> Dict[str, str]:
    """Clear durable budget ledger for test isolation."""
    manager = get_default_budget_ledger_manager()
    manager.reset()
    return {"status": "reset_completed"}
