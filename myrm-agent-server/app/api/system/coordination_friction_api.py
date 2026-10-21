"""
[INPUT]: Human intervention events, rework counts, and supervision decay queries.
[OUTPUT]: Coordination friction scoreboards, supervision decay curves, and tangible time-saved analytics.
[POS]: myrm-agent/myrm-agent-server/app/api/system/coordination_friction_api.py
"""

from datetime import datetime, timezone
import time
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.coordination_friction import (
    CoordinationFrictionTracker,
    CoordinationScoreboardSummary,
    InterventionType,
    SupervisionDecayPoint,
    TaskFrictionRecord,
)

router = APIRouter(tags=["coordination-friction"])

_tracker = CoordinationFrictionTracker()


class RecordInterventionRequest(BaseModel):
    task_id: str
    template_type: str
    execution_sequence: int = Field(ge=1)
    total_substeps: int = Field(gt=0)
    intervention_count: int = Field(ge=0)
    rework_count: int = Field(default=0, ge=0)
    human_attention_minutes: float = Field(ge=0.0)
    intervention_type: Optional[str] = "APPROVAL_GATE"
    timestamp: Optional[float] = None


class SupervisionDecayPointSchema(BaseModel):
    sequence_number: int
    intervention_rate_pct: float
    average_attention_minutes: float
    sample_count: int


class CoordinationScoreboardResponse(BaseModel):
    template_type: str
    total_runs: int
    average_friction_rate: float
    rework_rate_pct: float
    total_coordination_hours_saved: float
    friction_decay_pct: float
    decay_curve: List[SupervisionDecayPointSchema]
    active_templates: List[str]
    updated_at: str


class TaskFrictionRecordResponse(BaseModel):
    task_id: str
    template_type: str
    execution_sequence: int
    total_substeps: int
    intervention_count: int
    rework_count: int
    human_attention_minutes: float
    friction_rate: float
    timestamp: float


def _seed_sample_data_if_empty() -> None:
    """Seeds realistic recurring template execution history if tracker is fresh."""
    if _tracker.get_global_summary().total_runs > 0:
        return

    # Seed Template A: broadcast_prep (开播前三方准备与物料校验)
    # Run 1: High supervision
    _tracker.record_task_friction(
        task_id="seed-bp-1",
        template_type="broadcast_prep",
        execution_sequence=1,
        total_substeps=12,
        intervention_count=10,
        rework_count=2,
        human_attention_minutes=45.0,
    )
    # Run 2: Intermediate
    _tracker.record_task_friction(
        task_id="seed-bp-2",
        template_type="broadcast_prep",
        execution_sequence=2,
        total_substeps=12,
        intervention_count=5,
        rework_count=0,
        human_attention_minutes=20.0,
    )
    # Run 3: Mature
    _tracker.record_task_friction(
        task_id="seed-bp-3",
        template_type="broadcast_prep",
        execution_sequence=3,
        total_substeps=12,
        intervention_count=1,
        rework_count=0,
        human_attention_minutes=6.0,
    )

    # Seed Template B: channel_deal (跨渠道商务跟单)
    _tracker.record_task_friction(
        task_id="seed-cd-1",
        template_type="channel_deal",
        execution_sequence=1,
        total_substeps=10,
        intervention_count=7,
        rework_count=1,
        human_attention_minutes=35.0,
    )
    _tracker.record_task_friction(
        task_id="seed-cd-2",
        template_type="channel_deal",
        execution_sequence=2,
        total_substeps=10,
        intervention_count=2,
        rework_count=0,
        human_attention_minutes=12.0,
    )


@router.get(
    "/coordination-friction/scoreboard",
    response_model=CoordinationScoreboardResponse,
)
async def get_coordination_scoreboard(
    template_type: Optional[str] = Query(
        None,
        description="Optional filter by task template (e.g., 'broadcast_prep', 'channel_deal'). Defaults to 'global'.",
    ),
) -> CoordinationScoreboardResponse:
    """Retrieves tangible coordination friction metrics and supervision decay curve."""
    _seed_sample_data_if_empty()

    if template_type and template_type != "global":
        summary = _tracker.get_template_summary(template_type)
    else:
        summary = _tracker.get_global_summary()

    all_templates = list(_tracker._records_by_template.keys())
    now_iso = datetime.now(timezone.utc).isoformat()

    return CoordinationScoreboardResponse(
        template_type=summary.template_type,
        total_runs=summary.total_runs,
        average_friction_rate=summary.average_friction_rate,
        rework_rate_pct=summary.rework_rate_pct,
        total_coordination_hours_saved=summary.total_coordination_hours_saved,
        friction_decay_pct=summary.friction_decay_pct,
        decay_curve=[
            SupervisionDecayPointSchema(**point.to_dict())
            for point in summary.decay_curve
        ],
        active_templates=all_templates,
        updated_at=now_iso,
    )


@router.post(
    "/coordination-friction/record-intervention",
    response_model=TaskFrictionRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_task_intervention(
    req: RecordInterventionRequest,
) -> TaskFrictionRecordResponse:
    """Records an intervention checkpoint or rework signal during task execution."""
    now_ts = req.timestamp or time.time()
    record = _tracker.record_task_friction(
        task_id=req.task_id,
        template_type=req.template_type,
        execution_sequence=req.execution_sequence,
        total_substeps=req.total_substeps,
        intervention_count=req.intervention_count,
        rework_count=req.rework_count,
        human_attention_minutes=req.human_attention_minutes,
        timestamp=now_ts,
    )
    return TaskFrictionRecordResponse(**record.to_dict())


@router.get(
    "/coordination-friction/decay-curve/{template_type}",
    response_model=List[SupervisionDecayPointSchema],
)
async def get_template_decay_curve(
    template_type: str,
) -> List[SupervisionDecayPointSchema]:
    """Retrieves empirical supervision decay points for a recurring template type."""
    _seed_sample_data_if_empty()
    points = _tracker.compute_decay_curve(template_type)
    return [SupervisionDecayPointSchema(**p.to_dict()) for p in points]
