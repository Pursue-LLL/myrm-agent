"""
[INPUT]: Six-dimensional usage events, reconciliation invoices, and ledger queries.
[OUTPUT]: Pydantic schemas and REST endpoints for composite session-model-task usage ledger and dual-track reconciliation.
[POS]: myrm-agent/myrm-agent-server/app/api/system/composite_usage_ledger_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.composite_usage_ledger import (
    CompositeUsageRecord,
    CostReconciliationStatus,
    LedgerSummary,
    get_default_composite_usage_ledger,
)

router = APIRouter(prefix="/composite-usage-ledger", tags=["composite-usage-ledger"])


# --- Pydantic Request & Response Schemas ---


class RecordUsageRequest(BaseModel):
    session_id: str = Field(..., description="Target session identifier")
    model: str = Field(..., description="Target model name")
    billing_provider: str = Field(default="default_provider", description="LLM provider name")
    billing_base_url: str = Field(default="https://api.openai.com/v1", description="Provider endpoint URL")
    billing_mode: str = Field(default="standard", description="standard, stream, batch, etc.")
    task: str = Field(default="main_turn", description="Fine-grained task attribution dimension")
    input_tokens: int = Field(default=0, ge=0, description="Input tokens consumed")
    output_tokens: int = Field(default=0, ge=0, description="Output tokens generated")
    cache_read_tokens: int = Field(default=0, ge=0, description="Cached prompt tokens read")
    cache_write_tokens: int = Field(default=0, ge=0, description="Cache checkpoint tokens written")
    reasoning_tokens: int = Field(default=0, ge=0, description="Thinking or CoT tokens consumed")
    estimated_cost_usd: float = Field(default=0.0, ge=0.0, description="Locally estimated cost in USD")
    actual_cost_usd: float = Field(default=0.0, ge=0.0, description="Billed upstream invoice cost if available")


class ReconcileInvoiceRequest(BaseModel):
    session_id: str = Field(..., description="Target session identifier")
    model: str = Field(..., description="Target model name")
    billing_provider: str = Field(default="default_provider", description="LLM provider name")
    billing_base_url: str = Field(default="https://api.openai.com/v1", description="Provider endpoint URL")
    billing_mode: str = Field(default="standard", description="standard, stream, batch, etc.")
    task: str = Field(default="main_turn", description="Fine-grained task attribution dimension")
    actual_cost_usd: float = Field(..., ge=0.0, description="Actual billed cost returned from upstream provider")


class ResetLedgerRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Optional session id to clear, or null for all")


class CompositeUsageRecordModel(BaseModel):
    session_id: str
    model: str
    billing_provider: str
    billing_base_url: str
    billing_mode: str
    task: str
    api_call_count: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    estimated_cost_usd: float
    actual_cost_usd: float
    cost_status: str
    discrepancy_pct: float
    first_seen_ms: int
    last_seen_ms: int


class LedgerSummaryResponse(BaseModel):
    total_records: int
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_tokens: int
    total_estimated_usd: float
    total_actual_usd: float
    reconciled_records_count: int
    discrepancy_records_count: int
    task_spend_distribution: Dict[str, float]
    model_spend_distribution: Dict[str, float]


# --- Helper Converters ---


def _to_record_model(record: CompositeUsageRecord) -> CompositeUsageRecordModel:
    return CompositeUsageRecordModel(
        session_id=record.key.session_id,
        model=record.key.model,
        billing_provider=record.key.billing_provider,
        billing_base_url=record.key.billing_base_url,
        billing_mode=record.key.billing_mode,
        task=record.key.task,
        api_call_count=record.api_call_count,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cache_read_tokens=record.cache_read_tokens,
        cache_write_tokens=record.cache_write_tokens,
        reasoning_tokens=record.reasoning_tokens,
        estimated_cost_usd=round(record.estimated_cost_usd, 6),
        actual_cost_usd=round(record.actual_cost_usd, 6),
        cost_status=record.cost_status.value,
        discrepancy_pct=record.discrepancy_pct,
        first_seen_ms=record.first_seen_ms,
        last_seen_ms=record.last_seen_ms,
    )


def _to_summary_response(summary: LedgerSummary) -> LedgerSummaryResponse:
    return LedgerSummaryResponse(
        total_records=summary.total_records,
        total_calls=summary.total_calls,
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        total_cache_tokens=summary.total_cache_tokens,
        total_estimated_usd=summary.total_estimated_usd,
        total_actual_usd=summary.total_actual_usd,
        reconciled_records_count=summary.reconciled_records_count,
        discrepancy_records_count=summary.discrepancy_records_count,
        task_spend_distribution=summary.task_spend_distribution,
        model_spend_distribution=summary.model_spend_distribution,
    )


# --- Endpoints ---


@router.post("/record", response_model=CompositeUsageRecordModel)
async def record_usage(req: RecordUsageRequest) -> CompositeUsageRecordModel:
    """Record or accumulate LLM usage against the 6-dimensional composite key."""
    ledger = get_default_composite_usage_ledger()
    record = ledger.record_usage(
        session_id=req.session_id,
        model=req.model,
        billing_provider=req.billing_provider,
        billing_base_url=req.billing_base_url,
        billing_mode=req.billing_mode,
        task=req.task,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        cache_read_tokens=req.cache_read_tokens,
        cache_write_tokens=req.cache_write_tokens,
        reasoning_tokens=req.reasoning_tokens,
        estimated_cost_usd=req.estimated_cost_usd,
        actual_cost_usd=req.actual_cost_usd,
    )
    return _to_record_model(record)


@router.post("/reconcile", response_model=Optional[CompositeUsageRecordModel])
async def reconcile_invoice(req: ReconcileInvoiceRequest) -> Optional[CompositeUsageRecordModel]:
    """Apply upstream invoice billed cost and perform tolerance-based reconciliation."""
    ledger = get_default_composite_usage_ledger()
    record = ledger.reconcile_invoice(
        session_id=req.session_id,
        model=req.model,
        billing_provider=req.billing_provider,
        billing_base_url=req.billing_base_url,
        billing_mode=req.billing_mode,
        task=req.task,
        actual_cost_usd=req.actual_cost_usd,
    )
    if record is None:
        return None
    return _to_record_model(record)


@router.get("/records", response_model=List[CompositeUsageRecordModel])
async def get_ledger_records(
    session_id: Optional[str] = Query(None, description="Optional filter by session ID"),
    task: Optional[str] = Query(None, description="Optional filter by task attribution"),
    model: Optional[str] = Query(None, description="Optional filter by model"),
    limit: int = Query(100, ge=1, le=500, description="Max records to return"),
) -> List[CompositeUsageRecordModel]:
    """Retrieve fine-grained composite usage ledger rows."""
    ledger = get_default_composite_usage_ledger()
    records = ledger.get_records(session_id=session_id, task=task, model=model, limit=limit)
    return [_to_record_model(r) for r in records]


@router.get("/summary", response_model=LedgerSummaryResponse)
async def get_ledger_summary(
    session_id: Optional[str] = Query(None, description="Optional scope to a single session"),
) -> LedgerSummaryResponse:
    """Retrieve aggregated portfolio summary and dimensional breakdowns."""
    ledger = get_default_composite_usage_ledger()
    summary = ledger.get_summary(session_id=session_id)
    return _to_summary_response(summary)


@router.post("/reset")
async def reset_ledger(req: Optional[ResetLedgerRequest] = None) -> Dict[str, bool]:
    """Reset composite usage records globally or for a specific session."""
    ledger = get_default_composite_usage_ledger()
    sid = req.session_id if req else None
    ledger.reset(session_id=sid)
    return {"ok": True}
