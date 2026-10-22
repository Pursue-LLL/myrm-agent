"""
[INPUT]: Unattended run reliability records, benchmark triggers, and evaluation queries.
[OUTPUT]: ReliabilityTriadScoreResponse, record models, and REST endpoints for unattended reliability triad self-proof.
[POS]: myrm-agent/myrm-agent-server/app/api/system/unattended_reliability_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.unattended_reliability import (
    FinalReportingStatus,
    ReliabilityTriadScore,
    ResumeStatus,
    RunReliabilityRecord,
    SideEffectStatus,
    get_default_reliability_evaluator,
)

router = APIRouter(prefix="/unattended-reliability", tags=["unattended-reliability"])


# --- Pydantic Request & Response Schemas ---

class RecordRunRequest(BaseModel):
    task_name: str = Field(..., description="Unattended task name or identifier")
    resume_status: str = Field(
        default="NOT_APPLICABLE",
        description="RESUMED_SUCCESS, RESUMED_FAILED, NOT_APPLICABLE",
    )
    side_effect_status: str = Field(
        default="ZERO_DUPLICATE",
        description="ZERO_DUPLICATE, DUPLICATE_DETECTED, NO_SIDE_EFFECTS",
    )
    reporting_status: str = Field(
        default="GENUINE_SUCCESS",
        description="GENUINE_SUCCESS, HONEST_BLOCKER, HALLUCINATED_SUCCESS",
    )
    detail: str = Field(default="", description="Audit diagnosis or context details")
    run_id: Optional[str] = Field(default=None, description="Optional custom run id")


class RunReliabilityRecordModel(BaseModel):
    run_id: str
    task_name: str
    resume_status: str
    side_effect_status: str
    reporting_status: str
    detail: str
    timestamp_ms: int


class ReliabilityTriadScoreResponse(BaseModel):
    total_evaluated_runs: int
    resume_rate_pct: float
    zero_duplicate_side_effect_rate_pct: float
    honest_blocker_rate_pct: float
    composite_triad_score: float
    hallucinated_success_count: int
    duplicate_side_effect_count: int
    failed_resume_count: int
    recent_records: List[RunReliabilityRecordModel]


# --- Helper Converters ---

def _to_record_model(record: RunReliabilityRecord) -> RunReliabilityRecordModel:
    return RunReliabilityRecordModel(
        run_id=record.run_id,
        task_name=record.task_name,
        resume_status=record.resume_status.value,
        side_effect_status=record.side_effect_status.value,
        reporting_status=record.reporting_status.value,
        detail=record.detail,
        timestamp_ms=record.timestamp_ms,
    )


def _to_score_response(score: ReliabilityTriadScore) -> ReliabilityTriadScoreResponse:
    return ReliabilityTriadScoreResponse(
        total_evaluated_runs=score.total_evaluated_runs,
        resume_rate_pct=score.resume_rate_pct,
        zero_duplicate_side_effect_rate_pct=score.zero_duplicate_side_effect_rate_pct,
        honest_blocker_rate_pct=score.honest_blocker_rate_pct,
        composite_triad_score=score.composite_triad_score,
        hallucinated_success_count=score.hallucinated_success_count,
        duplicate_side_effect_count=score.duplicate_side_effect_count,
        failed_resume_count=score.failed_resume_count,
        recent_records=[_to_record_model(r) for r in score.recent_records],
    )


# --- Endpoints ---

@router.get("/score", response_model=ReliabilityTriadScoreResponse)
async def get_triad_score() -> ReliabilityTriadScoreResponse:
    """Retrieve full unattended reliability triad scorecard and recent proof logs."""
    evaluator = get_default_reliability_evaluator()
    score = evaluator.get_triad_score()
    return _to_score_response(score)


@router.post("/record", response_model=RunReliabilityRecordModel)
async def record_run(req: RecordRunRequest) -> RunReliabilityRecordModel:
    """Record an unattended agent run across restart, side-effect, and veracity dimensions."""
    evaluator = get_default_reliability_evaluator()
    record = evaluator.record_run(
        task_name=req.task_name,
        resume_status=req.resume_status,
        side_effect_status=req.side_effect_status,
        reporting_status=req.reporting_status,
        detail=req.detail,
        run_id=req.run_id,
    )
    return _to_record_model(record)


@router.post("/run-benchmark", response_model=ReliabilityTriadScoreResponse)
async def run_benchmark() -> ReliabilityTriadScoreResponse:
    """Execute built-in repeatable self-proof benchmark scenarios for unattended reliability."""
    evaluator = get_default_reliability_evaluator()
    score = evaluator.run_self_proof_benchmark()
    return _to_score_response(score)


@router.post("/reset")
async def reset_scores() -> Dict[str, bool]:
    """Reset evaluation history and counters."""
    evaluator = get_default_reliability_evaluator()
    evaluator.reset()
    return {"ok": True}
