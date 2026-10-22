"""
[INPUT]: Invocations captured inside ambient auxiliary contexts and reporting queries.
[OUTPUT]: Pydantic schemas and REST endpoints for ambient auxiliary usage accounting and task dimension attribution.
[POS]: myrm-agent/myrm-agent-server/app/api/system/ambient_auxiliary_accounting_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.ambient_auxiliary_accounting import (
    AmbientAccountingReport,
    AuxiliaryTaskType,
    AuxiliaryUsageSnapshot,
    TaskCostSummary,
    get_default_auxiliary_tracker,
)

router = APIRouter(prefix="/ambient-auxiliary", tags=["ambient-auxiliary"])


# --- Pydantic Request & Response Schemas ---


class RecordAuxiliaryInvocationRequest(BaseModel):
    session_id: str = Field(..., description="Target session identifier")
    input_tokens: int = Field(default=0, ge=0, description="Input tokens consumed")
    output_tokens: int = Field(default=0, ge=0, description="Output tokens generated")
    duration_ms: float = Field(default=0.0, ge=0.0, description="Call latency in milliseconds")
    cost_usd: float = Field(default=0.0, ge=0.0, description="Call cost in USD")
    task_type: Optional[str] = Field(default=None, description="Task taxonomy dimension (e.g. vision_prep, context_compression)")
    custom_task_name: str = Field(default="", description="Optional custom task identifier")
    model: str = Field(default="", description="Target model name")


class ResetAuxiliaryRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Optional session id to clear, or null for all")


class AuxiliaryUsageSnapshotModel(BaseModel):
    session_id: str
    task_type: str
    custom_task_name: str
    effective_task_name: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_ms: float
    cost_usd: float
    timestamp_ms: int


class TaskCostSummaryModel(BaseModel):
    task_name: str
    call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cost_usd: float
    avg_duration_ms: float
    share_pct: float


class AmbientAccountingReportModel(BaseModel):
    total_invocations: int
    total_cost_usd: float
    core_dialogue_cost_usd: float
    auxiliary_cost_usd: float
    auxiliary_cost_share_pct: float
    task_summaries: List[TaskCostSummaryModel]
    prompt_cache_purity_preserved: bool
    generated_at_ms: int


# --- Helper Converters ---


def _to_snapshot_model(snapshot: AuxiliaryUsageSnapshot) -> AuxiliaryUsageSnapshotModel:
    return AuxiliaryUsageSnapshotModel(
        session_id=snapshot.session_id,
        task_type=snapshot.task_type.value,
        custom_task_name=snapshot.custom_task_name,
        effective_task_name=snapshot.effective_task_name,
        model=snapshot.model,
        input_tokens=snapshot.input_tokens,
        output_tokens=snapshot.output_tokens,
        total_tokens=snapshot.input_tokens + snapshot.output_tokens,
        duration_ms=snapshot.duration_ms,
        cost_usd=round(snapshot.cost_usd, 6),
        timestamp_ms=snapshot.timestamp_ms,
    )


def _to_report_model(report: AmbientAccountingReport) -> AmbientAccountingReportModel:
    return AmbientAccountingReportModel(
        total_invocations=report.total_invocations,
        total_cost_usd=report.total_cost_usd,
        core_dialogue_cost_usd=report.core_dialogue_cost_usd,
        auxiliary_cost_usd=report.auxiliary_cost_usd,
        auxiliary_cost_share_pct=report.auxiliary_cost_share_pct,
        task_summaries=[
            TaskCostSummaryModel(
                task_name=t.task_name,
                call_count=t.call_count,
                total_input_tokens=t.total_input_tokens,
                total_output_tokens=t.total_output_tokens,
                total_tokens=t.total_tokens,
                total_cost_usd=t.total_cost_usd,
                avg_duration_ms=t.avg_duration_ms,
                share_pct=t.share_pct,
            )
            for t in report.task_summaries
        ],
        prompt_cache_purity_preserved=report.prompt_cache_purity_preserved,
        generated_at_ms=report.generated_at_ms,
    )


# --- Endpoints ---


@router.post("/record", response_model=AuxiliaryUsageSnapshotModel)
async def record_auxiliary_invocation(req: RecordAuxiliaryInvocationRequest) -> AuxiliaryUsageSnapshotModel:
    """Record LLM/tool usage, attributing to the ambient or explicitly specified task dimension."""
    tracker = get_default_auxiliary_tracker()
    snapshot = tracker.record_invocation(
        session_id=req.session_id,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        duration_ms=req.duration_ms,
        cost_usd=req.cost_usd,
        task_type=req.task_type,
        custom_task_name=req.custom_task_name,
        model=req.model,
    )
    return _to_snapshot_model(snapshot)


@router.get("/report", response_model=AmbientAccountingReportModel)
async def get_accounting_report(
    session_id: Optional[str] = Query(None, description="Optional scope to a single session ID"),
) -> AmbientAccountingReportModel:
    """Retrieve breakdown report comparing core dialogue vs auxiliary sub-task footprints."""
    tracker = get_default_auxiliary_tracker()
    report = tracker.get_accounting_report(session_id=session_id)
    return _to_report_model(report)


@router.get("/recent-snapshots", response_model=List[AuxiliaryUsageSnapshotModel])
async def get_recent_snapshots(
    session_id: Optional[str] = Query(None, description="Optional session filter"),
    limit: int = Query(50, ge=1, le=200, description="Max snapshots to return"),
) -> List[AuxiliaryUsageSnapshotModel]:
    """Retrieve recent usage snapshots partitioned by task dimension."""
    tracker = get_default_auxiliary_tracker()
    snapshots = tracker.get_recent_snapshots(session_id=session_id, limit=limit)
    return [_to_snapshot_model(s) for s in snapshots]


@router.post("/reset")
async def reset_auxiliary_accounting(req: Optional[ResetAuxiliaryRequest] = None) -> Dict[str, bool]:
    """Reset auxiliary accounting telemetry globally or for a specific session."""
    tracker = get_default_auxiliary_tracker()
    sid = req.session_id if req else None
    tracker.reset(session_id=sid)
    return {"ok": True}
