"""Assessment import funnel observability API.

[INPUT]
- app.database.models::AssessmentImportMetricEvent (POS: observability event ORM model)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- POST /statistics/assessment-import/events
- GET /statistics/assessment-import/summary

[POS]
Collect and aggregate assessment import funnel events:
attempt/success/failure + failure reason + entry trigger mix.
Value-summary (post-import execution anchors) lives in assessment_import_value.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import AssessmentImportMetricEvent

router = APIRouter()
logger = logging.getLogger(__name__)

_SURFACES = ("project_milestone_panel",)
_TRIGGERS = ("manual_input", "recent_candidate")
_RETENTION_DAYS = 90
_CLEANUP_MIN_INTERVAL = timedelta(hours=6)
_cleanup_lock = asyncio.Lock()
_last_cleanup_at: datetime | None = None

# Contract source: frontend assessmentImportError.ts::AssessmentImportFailureReason
AssessmentImportFailureReason = Literal[
    "artifact_version_already_imported",
    "no_actionable_tasks",
    "no_importable_tasks",
    "artifact_not_found",
    "project_not_found",
    "network_error",
    "unknown_error",
]


class AssessmentImportEventRequest(BaseModel):
    event_type: Literal[
        "import_attempted",
        "import_succeeded",
        "import_failed",
        "dropped_report",
    ]
    surface: Literal["project_milestone_panel"]
    trigger: Literal["manual_input", "recent_candidate"]
    context_key: str | None = Field(default=None, min_length=1, max_length=128)
    failure_reason: AssessmentImportFailureReason | None = None
    count: int = Field(default=1, ge=1, le=200)


class AssessmentImportSummaryResponse(BaseModel):
    days: int
    retention_days: int
    total_events: int
    import_attempted_count: int
    import_succeeded_count: int
    import_failed_count: int
    dropped_event_count: int
    success_rate: float
    failure_rate: float
    recent_candidate_attempt_rate: float
    attempts_by_trigger: dict[str, int]
    successes_by_trigger: dict[str, int]
    failures_by_trigger: dict[str, int]
    failure_reason_breakdown: dict[str, int]



def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _normalize_context_key(context_key: str | None) -> str | None:
    normalized = context_key.strip() if context_key else ""
    return normalized or None


def _normalize_failure_reason(
    event_type: str,
    failure_reason: AssessmentImportFailureReason | None,
) -> AssessmentImportFailureReason | None:
    if event_type == "import_failed":
        return failure_reason or "unknown_error"
    if failure_reason is not None:
        raise validation_error("failure_reason is only valid for import_failed")
    return None


def _validate_metric_fields(payload: AssessmentImportEventRequest) -> None:
    if payload.event_type != "dropped_report" and payload.count != 1:
        raise validation_error("count must be 1 except for dropped_report")



async def _maybe_prune_old_events(db: AsyncSession) -> int:
    """Best-effort periodic cleanup for old assessment import events."""
    global _last_cleanup_at

    now = datetime.now(timezone.utc)
    if _last_cleanup_at is not None and now - _last_cleanup_at < _CLEANUP_MIN_INTERVAL:
        return 0

    async with _cleanup_lock:
        now = datetime.now(timezone.utc)
        if _last_cleanup_at is not None and now - _last_cleanup_at < _CLEANUP_MIN_INTERVAL:
            return 0

        cutoff = now - timedelta(days=_RETENTION_DAYS)
        prune_stmt = (
            delete(AssessmentImportMetricEvent)
            .where(AssessmentImportMetricEvent.created_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(prune_stmt)
        await db.commit()
        _last_cleanup_at = now
        return int(result.rowcount or 0)


async def _sum_event_count(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> int:
    stmt = select(func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0)).where(
        and_(
            AssessmentImportMetricEvent.created_at >= start_dt,
            AssessmentImportMetricEvent.event_type == event_type,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def _trigger_breakdown(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> dict[str, int]:
    stmt = (
        select(
            AssessmentImportMetricEvent.trigger,
            func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0),
        )
        .where(
            and_(
                AssessmentImportMetricEvent.created_at >= start_dt,
                AssessmentImportMetricEvent.event_type == event_type,
            )
        )
        .group_by(AssessmentImportMetricEvent.trigger)
    )
    rows = (await db.execute(stmt)).all()
    breakdown = {trigger: 0 for trigger in _TRIGGERS}
    for trigger, total in rows:
        key = str(trigger)
        if key in breakdown:
            breakdown[key] = int(total or 0)
    return breakdown


async def _failure_reason_breakdown(
    db: AsyncSession,
    start_dt: datetime,
) -> dict[str, int]:
    stmt = (
        select(
            AssessmentImportMetricEvent.failure_reason,
            func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0),
        )
        .where(
            and_(
                AssessmentImportMetricEvent.created_at >= start_dt,
                AssessmentImportMetricEvent.event_type == "import_failed",
                AssessmentImportMetricEvent.failure_reason.isnot(None),
            )
        )
        .group_by(AssessmentImportMetricEvent.failure_reason)
    )
    rows = (await db.execute(stmt)).all()
    return {str(reason): int(total or 0) for reason, total in rows if reason}


@router.post("/assessment-import/events", response_model=None)
async def record_assessment_import_event(
    payload: AssessmentImportEventRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Record one assessment import funnel event."""
    try:
        _validate_metric_fields(payload)
        failure_reason = _normalize_failure_reason(payload.event_type, payload.failure_reason)
        event = AssessmentImportMetricEvent(
            event_type=payload.event_type,
            surface=payload.surface,
            trigger=payload.trigger,
            context_key=_normalize_context_key(payload.context_key),
            failure_reason=failure_reason,
            count=payload.count,
        )
        db.add(event)
        await db.commit()
        await _maybe_prune_old_events(db)
        return success_response(data={"accepted": True})
    except Exception as exc:
        if getattr(exc, "status_code", None) == 400:
            raise
        logger.exception("Assessment import metric ingest failed")
        raise internal_error(operation="Record assessment import event", exception=exc) from exc


@router.get("/assessment-import/summary")
async def get_assessment_import_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return assessment import funnel summary."""
    try:
        await _maybe_prune_old_events(db)
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)

        total_stmt = select(func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0)).where(
            AssessmentImportMetricEvent.created_at >= start_dt
        )
        total_events = int((await db.execute(total_stmt)).scalar() or 0)

        attempted_count = await _sum_event_count(db, start_dt, "import_attempted")
        succeeded_count = await _sum_event_count(db, start_dt, "import_succeeded")
        failed_count = await _sum_event_count(db, start_dt, "import_failed")
        dropped_count = await _sum_event_count(db, start_dt, "dropped_report")

        attempts_by_trigger = await _trigger_breakdown(db, start_dt, "import_attempted")
        successes_by_trigger = await _trigger_breakdown(db, start_dt, "import_succeeded")
        failures_by_trigger = await _trigger_breakdown(db, start_dt, "import_failed")
        failure_reason_breakdown = await _failure_reason_breakdown(db, start_dt)

        summary = AssessmentImportSummaryResponse(
            days=days,
            retention_days=_RETENTION_DAYS,
            total_events=total_events,
            import_attempted_count=attempted_count,
            import_succeeded_count=succeeded_count,
            import_failed_count=failed_count,
            dropped_event_count=dropped_count,
            success_rate=_safe_rate(succeeded_count, attempted_count),
            failure_rate=_safe_rate(failed_count, attempted_count),
            recent_candidate_attempt_rate=_safe_rate(
                attempts_by_trigger.get("recent_candidate", 0),
                attempted_count,
            ),
            attempts_by_trigger=attempts_by_trigger,
            successes_by_trigger=successes_by_trigger,
            failures_by_trigger=failures_by_trigger,
            failure_reason_breakdown=failure_reason_breakdown,
        )
        return success_response(data=summary.model_dump(mode="json"))
    except Exception as exc:
        if getattr(exc, "status_code", None) == 400:
            raise
        logger.exception("Assessment import summary failed")
        raise internal_error(operation="Get assessment import summary", exception=exc) from exc


