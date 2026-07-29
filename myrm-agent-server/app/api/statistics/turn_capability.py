"""Turn capability observability API.

[INPUT]
- app.database.models::TurnCapabilityMetricEvent (POS: observability event ORM model)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- POST /statistics/turn-capability/events
- GET /statistics/turn-capability/summary

[POS]
Collect and aggregate one-turn Skill/MCP capability override observability:
submission/apply/noop/queue/completion/failure/busy-requeue and dropped telemetry.
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
from app.database.models import TurnCapabilityMetricEvent

router = APIRouter()
logger = logging.getLogger(__name__)

_SOURCES = ("direct", "queue_submit", "queue_drain", "busy_requeue")
_RETENTION_DAYS = 90
_CLEANUP_MIN_INTERVAL = timedelta(hours=6)
_cleanup_lock = asyncio.Lock()
_last_cleanup_at: datetime | None = None

TurnCapabilityFailureReason = Literal[
    "network_error",
    "archive_restore_invalid",
    "abort",
    "server_error",
    "unknown_error",
]


class TurnCapabilityEventRequest(BaseModel):
    event_type: Literal[
        "selection_submitted",
        "override_applied",
        "override_noop",
        "queue_enqueued",
        "send_completed",
        "send_failed",
        "busy_requeued",
        "dropped_report",
    ]
    source: Literal["direct", "queue_submit", "queue_drain", "busy_requeue"]
    context_key: str | None = Field(default=None, min_length=1, max_length=128)
    count: int = Field(default=1, ge=1, le=200)
    selected_skill_count: int | None = Field(default=None, ge=0, le=500)
    selected_mcp_count: int | None = Field(default=None, ge=0, le=500)
    effective_skill_count: int | None = Field(default=None, ge=0, le=500)
    effective_mcp_count: int | None = Field(default=None, ge=0, le=500)
    failure_reason: TurnCapabilityFailureReason | None = None


class TurnCapabilitySummaryResponse(BaseModel):
    days: int
    retention_days: int
    total_events: int
    selection_submitted_count: int
    override_applied_count: int
    override_noop_count: int
    queue_enqueued_count: int
    send_completed_count: int
    send_failed_count: int
    busy_requeued_count: int
    dropped_event_count: int
    apply_rate: float
    noop_rate: float
    queue_rate: float
    completion_rate: float
    failure_rate: float
    avg_selected_skill_count: float
    avg_selected_mcp_count: float
    avg_effective_skill_count: float
    avg_effective_mcp_count: float
    submitted_by_source: dict[str, int]
    applied_by_source: dict[str, int]
    completed_by_source: dict[str, int]
    failed_by_source: dict[str, int]
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
    failure_reason: TurnCapabilityFailureReason | None,
) -> TurnCapabilityFailureReason | None:
    if event_type == "send_failed":
        return failure_reason or "unknown_error"
    if failure_reason is not None:
        raise validation_error("failure_reason is only valid for send_failed")
    return None


def _validate_metric_fields(payload: TurnCapabilityEventRequest) -> None:
    selected_allowed = {"selection_submitted", "override_applied", "override_noop", "queue_enqueued"}
    effective_allowed = {"override_applied", "send_completed"}

    if payload.event_type != "dropped_report" and payload.count != 1:
        raise validation_error("count must be 1 except for dropped_report")

    if payload.selected_skill_count is not None and payload.event_type not in selected_allowed:
        raise validation_error("selected_skill_count is invalid for this event_type")
    if payload.selected_mcp_count is not None and payload.event_type not in selected_allowed:
        raise validation_error("selected_mcp_count is invalid for this event_type")
    if payload.effective_skill_count is not None and payload.event_type not in effective_allowed:
        raise validation_error("effective_skill_count is invalid for this event_type")
    if payload.effective_mcp_count is not None and payload.event_type not in effective_allowed:
        raise validation_error("effective_mcp_count is invalid for this event_type")

    if payload.event_type in {"override_applied", "send_completed"} and (
        payload.effective_skill_count is None or payload.effective_mcp_count is None
    ):
        raise validation_error("effective_skill_count/effective_mcp_count are required for this event_type")


async def _maybe_prune_old_events(db: AsyncSession) -> int:
    """Best-effort periodic cleanup for old turn capability events."""
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
            delete(TurnCapabilityMetricEvent)
            .where(TurnCapabilityMetricEvent.created_at < cutoff)
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
    stmt = select(func.coalesce(func.sum(TurnCapabilityMetricEvent.count), 0)).where(
        and_(
            TurnCapabilityMetricEvent.created_at >= start_dt,
            TurnCapabilityMetricEvent.event_type == event_type,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def _sum_weighted_count(
    db: AsyncSession,
    start_dt: datetime,
    column_name: str,
    event_types: tuple[str, ...],
) -> tuple[int, int]:
    column = getattr(TurnCapabilityMetricEvent, column_name)
    stmt = select(
        func.coalesce(func.sum(column * TurnCapabilityMetricEvent.count), 0),
        func.coalesce(func.sum(TurnCapabilityMetricEvent.count), 0),
    ).where(
        and_(
            TurnCapabilityMetricEvent.created_at >= start_dt,
            TurnCapabilityMetricEvent.event_type.in_(event_types),
            column.isnot(None),
        )
    )
    weighted_total, sample_count = (await db.execute(stmt)).one()
    return int(weighted_total or 0), int(sample_count or 0)


async def _source_breakdown(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> dict[str, int]:
    stmt = (
        select(
            TurnCapabilityMetricEvent.source,
            func.coalesce(func.sum(TurnCapabilityMetricEvent.count), 0),
        )
        .where(
            and_(
                TurnCapabilityMetricEvent.created_at >= start_dt,
                TurnCapabilityMetricEvent.event_type == event_type,
            )
        )
        .group_by(TurnCapabilityMetricEvent.source)
    )
    rows = (await db.execute(stmt)).all()
    result = {source: 0 for source in _SOURCES}
    for source, count in rows:
        if source in result:
            result[source] = int(count or 0)
    return result


async def _failure_reason_breakdown(
    db: AsyncSession,
    start_dt: datetime,
) -> dict[str, int]:
    stmt = (
        select(
            TurnCapabilityMetricEvent.failure_reason,
            func.coalesce(func.sum(TurnCapabilityMetricEvent.count), 0),
        )
        .where(
            and_(
                TurnCapabilityMetricEvent.created_at >= start_dt,
                TurnCapabilityMetricEvent.event_type == "send_failed",
            )
        )
        .group_by(TurnCapabilityMetricEvent.failure_reason)
    )
    rows = (await db.execute(stmt)).all()
    result: dict[str, int] = {}
    for reason, count in rows:
        key = reason or "unknown_error"
        result[key] = int(count or 0)
    return result


@router.post("/turn-capability/events")
async def ingest_turn_capability_event(
    payload: TurnCapabilityEventRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Ingest a one-turn capability observability event."""
    try:
        _validate_metric_fields(payload)
        normalized_reason = _normalize_failure_reason(payload.event_type, payload.failure_reason)
        event = TurnCapabilityMetricEvent(
            event_type=payload.event_type,
            source=payload.source,
            context_key=_normalize_context_key(payload.context_key),
            count=payload.count,
            selected_skill_count=payload.selected_skill_count,
            selected_mcp_count=payload.selected_mcp_count,
            effective_skill_count=payload.effective_skill_count,
            effective_mcp_count=payload.effective_mcp_count,
            failure_reason=normalized_reason,
        )
        db.add(event)
        await db.commit()
        pruned_events = await _maybe_prune_old_events(db)
        return success_response(data={"accepted": True, "pruned_events": pruned_events})
    except Exception as e:
        if getattr(e, "status_code", None) == 400:
            raise
        logger.exception("Turn capability metric ingest failed")
        raise internal_error(operation="Ingest turn capability event", exception=e) from e


@router.get("/turn-capability/summary")
async def get_turn_capability_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return aggregated one-turn capability observability summary."""
    try:
        await _maybe_prune_old_events(db)
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)

        selection_submitted_count = await _sum_event_count(db, start_dt, "selection_submitted")
        override_applied_count = await _sum_event_count(db, start_dt, "override_applied")
        override_noop_count = await _sum_event_count(db, start_dt, "override_noop")
        queue_enqueued_count = await _sum_event_count(db, start_dt, "queue_enqueued")
        send_completed_count = await _sum_event_count(db, start_dt, "send_completed")
        send_failed_count = await _sum_event_count(db, start_dt, "send_failed")
        busy_requeued_count = await _sum_event_count(db, start_dt, "busy_requeued")
        dropped_event_count = await _sum_event_count(db, start_dt, "dropped_report")

        total_events_stmt = select(func.coalesce(func.sum(TurnCapabilityMetricEvent.count), 0)).where(
            TurnCapabilityMetricEvent.created_at >= start_dt
        )
        total_events = int((await db.execute(total_events_stmt)).scalar() or 0)

        selected_skill_total, selected_skill_samples = await _sum_weighted_count(
            db,
            start_dt,
            "selected_skill_count",
            ("selection_submitted",),
        )
        selected_mcp_total, selected_mcp_samples = await _sum_weighted_count(
            db,
            start_dt,
            "selected_mcp_count",
            ("selection_submitted",),
        )
        effective_skill_total, effective_skill_samples = await _sum_weighted_count(
            db,
            start_dt,
            "effective_skill_count",
            ("override_applied",),
        )
        effective_mcp_total, effective_mcp_samples = await _sum_weighted_count(
            db,
            start_dt,
            "effective_mcp_count",
            ("override_applied",),
        )

        summary = TurnCapabilitySummaryResponse(
            days=days,
            retention_days=_RETENTION_DAYS,
            total_events=total_events,
            selection_submitted_count=selection_submitted_count,
            override_applied_count=override_applied_count,
            override_noop_count=override_noop_count,
            queue_enqueued_count=queue_enqueued_count,
            send_completed_count=send_completed_count,
            send_failed_count=send_failed_count,
            busy_requeued_count=busy_requeued_count,
            dropped_event_count=dropped_event_count,
            apply_rate=_safe_rate(override_applied_count, selection_submitted_count),
            noop_rate=_safe_rate(override_noop_count, selection_submitted_count),
            queue_rate=_safe_rate(queue_enqueued_count, selection_submitted_count),
            completion_rate=_safe_rate(send_completed_count, override_applied_count),
            failure_rate=_safe_rate(send_failed_count, override_applied_count),
            avg_selected_skill_count=_safe_avg(selected_skill_total, selected_skill_samples),
            avg_selected_mcp_count=_safe_avg(selected_mcp_total, selected_mcp_samples),
            avg_effective_skill_count=_safe_avg(effective_skill_total, effective_skill_samples),
            avg_effective_mcp_count=_safe_avg(effective_mcp_total, effective_mcp_samples),
            submitted_by_source=await _source_breakdown(db, start_dt, "selection_submitted"),
            applied_by_source=await _source_breakdown(db, start_dt, "override_applied"),
            completed_by_source=await _source_breakdown(db, start_dt, "send_completed"),
            failed_by_source=await _source_breakdown(db, start_dt, "send_failed"),
            failure_reason_breakdown=await _failure_reason_breakdown(db, start_dt),
        )
        return success_response(data=summary.model_dump(mode="json"))
    except Exception as e:
        if getattr(e, "status_code", None) == 400:
            raise
        logger.exception("Turn capability summary failed")
        raise internal_error(operation="Get turn capability summary", exception=e) from e
