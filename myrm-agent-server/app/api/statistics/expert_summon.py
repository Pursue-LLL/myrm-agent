"""Expert summon funnel observability API.

[INPUT]
- app.database.models::ExpertSummonMetricEvent (POS: observability event ORM model)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- POST /statistics/expert-summon/events
- GET /statistics/expert-summon/summary

[POS]
Collect and aggregate expert template summon funnel events:
surface exposure/search/adoption + summon conversion + post-summon first-message conversion.
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
from app.database.models import ExpertSummonMetricEvent

router = APIRouter()
logger = logging.getLogger(__name__)

_SURFACES = ("template_market", "flow_pad_inline")
_TRIGGERS = ("template_card", "use_case_chip", "route_menu")
_RETENTION_DAYS = 90
_CLEANUP_MIN_INTERVAL = timedelta(hours=6)
_cleanup_lock = asyncio.Lock()
_last_cleanup_at: datetime | None = None

ExpertSummonFailureReason = Literal[
    "network_error",
    "route_apply_failed",
    "server_error",
    "unknown_error",
]


class ExpertSummonEventRequest(BaseModel):
    event_type: Literal[
        "surface_viewed",
        "search_used",
        "summon_attempted",
        "summon_succeeded",
        "summon_failed",
        "route_applied",
        "route_apply_failed",
        "first_message_sent",
        "dropped_report",
    ]
    surface: Literal["template_market", "flow_pad_inline"]
    context_key: str | None = Field(default=None, min_length=1, max_length=128)
    trigger: Literal["template_card", "use_case_chip", "route_menu"] | None = None
    template_kind: Literal["team", "individual"] | None = None
    from_search: bool | None = None
    used_use_case: bool | None = None
    query_length: int | None = Field(default=None, ge=0, le=200)
    failure_reason: ExpertSummonFailureReason | None = None
    count: int = Field(default=1, ge=1, le=200)


class ExpertSummonSummaryResponse(BaseModel):
    days: int
    retention_days: int
    total_events: int
    surface_viewed_count: int
    search_used_count: int
    summon_attempted_count: int
    summon_succeeded_count: int
    summon_failed_count: int
    route_applied_count: int
    route_apply_failed_count: int
    first_message_sent_count: int
    dropped_event_count: int
    summon_success_rate: float
    summon_failure_rate: float
    route_apply_rate: float
    first_message_sent_rate: float
    use_case_trigger_rate: float
    search_assisted_summon_rate: float
    avg_search_query_length: float
    viewed_by_surface: dict[str, int]
    attempted_by_surface: dict[str, int]
    succeeded_by_surface: dict[str, int]
    failed_by_surface: dict[str, int]
    attempted_by_trigger: dict[str, int]
    failure_reason_breakdown: dict[str, int]


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _safe_avg(total: int, sample_count: int) -> float:
    if sample_count <= 0:
        return 0.0
    return round(total / sample_count, 2)


def _normalize_context_key(context_key: str | None) -> str | None:
    normalized = context_key.strip() if context_key else ""
    return normalized or None


def _normalize_failure_reason(
    event_type: str,
    failure_reason: ExpertSummonFailureReason | None,
) -> ExpertSummonFailureReason | None:
    if event_type in {"summon_failed", "route_apply_failed"}:
        return failure_reason or "unknown_error"
    if failure_reason is not None:
        raise validation_error("failure_reason is only valid for summon_failed/route_apply_failed")
    return None


def _validate_metric_fields(payload: ExpertSummonEventRequest) -> None:
    trigger_required_events = {
        "summon_attempted",
        "summon_succeeded",
        "summon_failed",
        "route_applied",
        "route_apply_failed",
        "first_message_sent",
    }
    trigger_forbidden_events = {"surface_viewed", "search_used", "dropped_report"}

    if payload.event_type != "dropped_report" and payload.count != 1:
        raise validation_error("count must be 1 except for dropped_report")

    if payload.event_type in trigger_required_events and payload.trigger is None:
        raise validation_error("trigger is required for this event_type")
    if payload.event_type in trigger_forbidden_events and payload.trigger is not None:
        raise validation_error("trigger is invalid for this event_type")

    if payload.query_length is not None and payload.event_type != "search_used":
        raise validation_error("query_length is only valid for search_used")


async def _maybe_prune_old_events(db: AsyncSession) -> int:
    """Best-effort periodic cleanup for old expert summon events."""
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
            delete(ExpertSummonMetricEvent)
            .where(ExpertSummonMetricEvent.created_at < cutoff)
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
    stmt = select(func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0)).where(
        and_(
            ExpertSummonMetricEvent.created_at >= start_dt,
            ExpertSummonMetricEvent.event_type == event_type,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def _surface_breakdown(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> dict[str, int]:
    stmt = (
        select(
            ExpertSummonMetricEvent.surface,
            func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0),
        )
        .where(
            and_(
                ExpertSummonMetricEvent.created_at >= start_dt,
                ExpertSummonMetricEvent.event_type == event_type,
            )
        )
        .group_by(ExpertSummonMetricEvent.surface)
    )
    rows = (await db.execute(stmt)).all()
    result = {surface: 0 for surface in _SURFACES}
    for surface, count in rows:
        if surface in result:
            result[surface] = int(count or 0)
    return result


async def _trigger_breakdown(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> dict[str, int]:
    stmt = (
        select(
            ExpertSummonMetricEvent.trigger,
            func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0),
        )
        .where(
            and_(
                ExpertSummonMetricEvent.created_at >= start_dt,
                ExpertSummonMetricEvent.event_type == event_type,
                ExpertSummonMetricEvent.trigger.isnot(None),
            )
        )
        .group_by(ExpertSummonMetricEvent.trigger)
    )
    rows = (await db.execute(stmt)).all()
    result = {trigger: 0 for trigger in _TRIGGERS}
    for trigger, count in rows:
        if trigger in result:
            result[trigger] = int(count or 0)
    return result


async def _failure_reason_breakdown(
    db: AsyncSession,
    start_dt: datetime,
) -> dict[str, int]:
    stmt = (
        select(
            ExpertSummonMetricEvent.failure_reason,
            func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0),
        )
        .where(
            and_(
                ExpertSummonMetricEvent.created_at >= start_dt,
                ExpertSummonMetricEvent.event_type.in_(("summon_failed", "route_apply_failed")),
            )
        )
        .group_by(ExpertSummonMetricEvent.failure_reason)
    )
    rows = (await db.execute(stmt)).all()
    result: dict[str, int] = {}
    for reason, count in rows:
        key = reason or "unknown_error"
        result[key] = int(count or 0)
    return result


async def _sum_boolean_flag(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
    column_name: str,
) -> int:
    column = getattr(ExpertSummonMetricEvent, column_name)
    stmt = select(func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0)).where(
        and_(
            ExpertSummonMetricEvent.created_at >= start_dt,
            ExpertSummonMetricEvent.event_type == event_type,
            column.is_(True),
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def _sum_weighted_query_length(
    db: AsyncSession,
    start_dt: datetime,
) -> tuple[int, int]:
    stmt = select(
        func.coalesce(func.sum(ExpertSummonMetricEvent.query_length * ExpertSummonMetricEvent.count), 0),
        func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0),
    ).where(
        and_(
            ExpertSummonMetricEvent.created_at >= start_dt,
            ExpertSummonMetricEvent.event_type == "search_used",
            ExpertSummonMetricEvent.query_length.isnot(None),
        )
    )
    weighted_total, sample_count = (await db.execute(stmt)).one()
    return int(weighted_total or 0), int(sample_count or 0)


@router.post("/expert-summon/events")
async def ingest_expert_summon_event(
    payload: ExpertSummonEventRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Ingest an expert summon funnel observability event."""
    try:
        _validate_metric_fields(payload)
        normalized_reason = _normalize_failure_reason(payload.event_type, payload.failure_reason)
        event = ExpertSummonMetricEvent(
            event_type=payload.event_type,
            surface=payload.surface,
            context_key=_normalize_context_key(payload.context_key),
            trigger=payload.trigger,
            template_kind=payload.template_kind,
            from_search=payload.from_search,
            used_use_case=payload.used_use_case,
            query_length=payload.query_length,
            failure_reason=normalized_reason,
            count=payload.count,
        )
        db.add(event)
        await db.commit()
        pruned_events = await _maybe_prune_old_events(db)
        return success_response(data={"accepted": True, "pruned_events": pruned_events})
    except Exception as e:
        if getattr(e, "status_code", None) == 400:
            raise
        logger.exception("Expert summon metric ingest failed")
        raise internal_error(operation="Ingest expert summon event", exception=e) from e


@router.get("/expert-summon/summary")
async def get_expert_summon_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return aggregated expert summon funnel observability summary."""
    try:
        await _maybe_prune_old_events(db)
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)

        surface_viewed_count = await _sum_event_count(db, start_dt, "surface_viewed")
        search_used_count = await _sum_event_count(db, start_dt, "search_used")
        summon_attempted_count = await _sum_event_count(db, start_dt, "summon_attempted")
        summon_succeeded_count = await _sum_event_count(db, start_dt, "summon_succeeded")
        summon_failed_count = await _sum_event_count(db, start_dt, "summon_failed")
        route_applied_count = await _sum_event_count(db, start_dt, "route_applied")
        route_apply_failed_count = await _sum_event_count(db, start_dt, "route_apply_failed")
        first_message_sent_count = await _sum_event_count(db, start_dt, "first_message_sent")
        dropped_event_count = await _sum_event_count(db, start_dt, "dropped_report")

        total_events_stmt = select(func.coalesce(func.sum(ExpertSummonMetricEvent.count), 0)).where(
            ExpertSummonMetricEvent.created_at >= start_dt
        )
        total_events = int((await db.execute(total_events_stmt)).scalar() or 0)

        use_case_attempted_count = await _sum_boolean_flag(db, start_dt, "summon_attempted", "used_use_case")
        search_assisted_attempted_count = await _sum_boolean_flag(db, start_dt, "summon_attempted", "from_search")
        query_length_total, query_length_samples = await _sum_weighted_query_length(db, start_dt)

        summary = ExpertSummonSummaryResponse(
            days=days,
            retention_days=_RETENTION_DAYS,
            total_events=total_events,
            surface_viewed_count=surface_viewed_count,
            search_used_count=search_used_count,
            summon_attempted_count=summon_attempted_count,
            summon_succeeded_count=summon_succeeded_count,
            summon_failed_count=summon_failed_count,
            route_applied_count=route_applied_count,
            route_apply_failed_count=route_apply_failed_count,
            first_message_sent_count=first_message_sent_count,
            dropped_event_count=dropped_event_count,
            summon_success_rate=_safe_rate(summon_succeeded_count, summon_attempted_count),
            summon_failure_rate=_safe_rate(summon_failed_count, summon_attempted_count),
            route_apply_rate=_safe_rate(route_applied_count, summon_succeeded_count),
            first_message_sent_rate=_safe_rate(first_message_sent_count, summon_succeeded_count),
            use_case_trigger_rate=_safe_rate(use_case_attempted_count, summon_attempted_count),
            search_assisted_summon_rate=_safe_rate(search_assisted_attempted_count, summon_attempted_count),
            avg_search_query_length=_safe_avg(query_length_total, query_length_samples),
            viewed_by_surface=await _surface_breakdown(db, start_dt, "surface_viewed"),
            attempted_by_surface=await _surface_breakdown(db, start_dt, "summon_attempted"),
            succeeded_by_surface=await _surface_breakdown(db, start_dt, "summon_succeeded"),
            failed_by_surface=await _surface_breakdown(db, start_dt, "summon_failed"),
            attempted_by_trigger=await _trigger_breakdown(db, start_dt, "summon_attempted"),
            failure_reason_breakdown=await _failure_reason_breakdown(db, start_dt),
        )
        return success_response(data=summary.model_dump(mode="json"))
    except Exception as e:
        if getattr(e, "status_code", None) == 400:
            raise
        logger.exception("Expert summon summary failed")
        raise internal_error(operation="Get expert summon summary", exception=e) from e
