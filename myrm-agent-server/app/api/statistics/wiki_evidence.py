"""Wiki evidence observability API.

[INPUT]
- app.database.models::WikiEvidenceMetricEvent (POS: observability event ORM model)
- app.database.models::SystemNotification (POS: persisted async notification model)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- POST /statistics/wiki-evidence/events
- GET /statistics/wiki-evidence/summary

[POS]
Collect and aggregate minimal wiki evidence verification metrics:
snippet expansion/deep verification/re-query/quick-bounce plus dwell metrics,
and negative quality outcomes from user regeneration/undo behavior,
with governance alert notifications when quality drops.
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

from app.api.statistics import wiki_evidence_alerts as wiki_evidence_alerts_core
from app.api.statistics.wiki_evidence_alerts import (
    maybe_emit_governance_alerts,
    reset_wiki_evidence_alert_state_for_test,
)
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import WikiEvidenceMetricEvent

router = APIRouter()
logger = logging.getLogger(__name__)

_SURFACES = ("chat", "settings")
_LEVELS = ("L0", "L1", "L2")
_RETENTION_DAYS = 90
_CLEANUP_MIN_INTERVAL = timedelta(hours=6)
_DEEP_VERIFICATION_THRESHOLD_MS = 8_000
_QUICK_BOUNCE_THRESHOLD_MS = 2_000
_QUALITY_OUTCOME_NEGATIVE_EVENT_TYPE = "quality_outcome_negative"
_ALERT_TRIGGER_EVENT_TYPES = frozenset(
    {"dropped_report", "snippet_open", "snippet_close", _QUALITY_OUTCOME_NEGATIVE_EVENT_TYPE}
)
_ALERT_DROPPED_EVENT_THRESHOLD = wiki_evidence_alerts_core._ALERT_DROPPED_EVENT_THRESHOLD
_ALERT_DEEP_VERIFICATION_MIN_OPEN_COUNT = (
    wiki_evidence_alerts_core._ALERT_DEEP_VERIFICATION_MIN_OPEN_COUNT
)
_ALERT_DEEP_VERIFICATION_MIN_DWELL_SAMPLES = (
    wiki_evidence_alerts_core._ALERT_DEEP_VERIFICATION_MIN_DWELL_SAMPLES
)
_ALERT_NEGATIVE_OUTCOME_MIN_EVIDENCE_SURFACE_COUNT = (
    wiki_evidence_alerts_core._ALERT_NEGATIVE_OUTCOME_MIN_EVIDENCE_SURFACE_COUNT
)
_ALERT_NEGATIVE_OUTCOME_RATE_THRESHOLD = wiki_evidence_alerts_core._ALERT_NEGATIVE_OUTCOME_RATE_THRESHOLD
_cleanup_lock = asyncio.Lock()
_last_cleanup_at: datetime | None = None


class WikiEvidenceEventRequest(BaseModel):
    event_type: Literal[
        "evidence_surface",
        "snippet_open",
        "snippet_close",
        "query_submitted",
        "dropped_report",
        "quality_outcome_negative",
    ]
    surface: Literal["chat", "settings"]
    context_key: str | None = Field(default=None, min_length=1, max_length=128)
    level: Literal["L0", "L1", "L2"] | None = None
    count: int = Field(default=1, ge=1, le=200)
    dwell_ms: int | None = Field(default=None, ge=0, le=1_800_000)
    after_evidence: bool | None = None


class WikiEvidenceSummaryResponse(BaseModel):
    days: int
    retention_days: int
    total_events: int
    evidence_surface_count: int
    snippet_open_count: int
    dropped_event_count: int
    snippet_expansion_rate: float
    deep_verification_count: int
    deep_verification_rate: float
    quick_bounce_count: int
    quick_bounce_rate: float
    quality_outcome_negative_count: int
    quality_outcome_negative_rate: float
    query_count: int
    requery_count: int
    requery_rate: float
    verification_dwell_avg_ms: float
    verification_dwell_sample_count: int
    snippet_open_by_surface: dict[str, int]
    snippet_open_by_level: dict[str, int]
    quality_outcome_negative_by_surface: dict[str, int]


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


async def _maybe_prune_old_events(db: AsyncSession) -> int:
    """Best-effort periodic cleanup for old evidence events."""
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
            delete(WikiEvidenceMetricEvent)
            .where(WikiEvidenceMetricEvent.created_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(prune_stmt)
        await db.commit()
        _last_cleanup_at = now
        return int(result.rowcount or 0)


@router.post("/wiki-evidence/events")
async def ingest_wiki_evidence_event(
    payload: WikiEvidenceEventRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Ingest a wiki evidence observability event."""
    try:
        if payload.event_type == "snippet_close" and payload.dwell_ms is None:
            raise validation_error("dwell_ms is required for snippet_close")
        if payload.event_type == "snippet_close" and payload.count != 1:
            raise validation_error("count must be 1 for snippet_close")
        if payload.event_type != "query_submitted" and payload.after_evidence is not None:
            raise validation_error("after_evidence is only valid for query_submitted")
        if payload.level is not None and payload.event_type != "snippet_open":
            raise validation_error("level is only valid for snippet_open")
        if payload.event_type == "dropped_report" and payload.dwell_ms is not None:
            raise validation_error("dwell_ms is invalid for dropped_report")
        if payload.event_type == "dropped_report" and payload.after_evidence is not None:
            raise validation_error("after_evidence is invalid for dropped_report")
        if payload.event_type == _QUALITY_OUTCOME_NEGATIVE_EVENT_TYPE and payload.dwell_ms is not None:
            raise validation_error("dwell_ms is invalid for quality_outcome_negative")

        event = WikiEvidenceMetricEvent(
            event_type=payload.event_type,
            surface=payload.surface,
            context_key=(payload.context_key.strip() if payload.context_key else None),
            level=payload.level,
            count=payload.count,
            dwell_ms=payload.dwell_ms,
            after_evidence=payload.after_evidence,
            meta_data=None,
        )
        db.add(event)
        await db.commit()
        pruned_events = await _maybe_prune_old_events(db)
        alerts_emitted = 0
        if payload.event_type in _ALERT_TRIGGER_EVENT_TYPES:
            alerts_emitted = await maybe_emit_governance_alerts(db)
        return success_response(data={"accepted": True, "pruned_events": pruned_events, "alerts_emitted": alerts_emitted})
    except Exception as e:
        if getattr(e, "status_code", None) == 400:
            raise
        logger.exception("Wiki evidence ingest failed")
        raise internal_error(operation="Ingest wiki evidence event", exception=e) from e


@router.get("/wiki-evidence/summary")
async def get_wiki_evidence_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return aggregated wiki evidence observability summary."""
    try:
        await _maybe_prune_old_events(db)
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        base_filters = (WikiEvidenceMetricEvent.created_at >= start_dt,)

        total_events_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(*base_filters)
        evidence_surface_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "evidence_surface",
            )
        )
        snippet_open_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "snippet_open",
            )
        )
        dropped_event_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "dropped_report",
            )
        )
        quality_outcome_negative_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == _QUALITY_OUTCOME_NEGATIVE_EVENT_TYPE,
            )
        )
        query_count_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "query_submitted",
            )
        )
        requery_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "query_submitted",
                WikiEvidenceMetricEvent.after_evidence.is_(True),
            )
        )
        dwell_stmt = select(
            func.coalesce(func.sum(WikiEvidenceMetricEvent.dwell_ms * WikiEvidenceMetricEvent.count), 0),
            func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0),
        ).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "snippet_close",
                WikiEvidenceMetricEvent.dwell_ms.isnot(None),
            )
        )
        deep_verification_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "snippet_close",
                WikiEvidenceMetricEvent.dwell_ms.isnot(None),
                WikiEvidenceMetricEvent.dwell_ms >= _DEEP_VERIFICATION_THRESHOLD_MS,
            )
        )
        quick_bounce_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
            and_(
                *base_filters,
                WikiEvidenceMetricEvent.event_type == "snippet_close",
                WikiEvidenceMetricEvent.dwell_ms.isnot(None),
                WikiEvidenceMetricEvent.dwell_ms <= _QUICK_BOUNCE_THRESHOLD_MS,
            )
        )

        surface_breakdown_stmt = (
            select(
                WikiEvidenceMetricEvent.surface,
                func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0),
            )
            .where(
                and_(
                    *base_filters,
                    WikiEvidenceMetricEvent.event_type == "snippet_open",
                )
            )
            .group_by(WikiEvidenceMetricEvent.surface)
        )
        evidence_surface_breakdown_stmt = (
            select(
                WikiEvidenceMetricEvent.surface,
                func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0),
            )
            .where(
                and_(
                    *base_filters,
                    WikiEvidenceMetricEvent.event_type == "evidence_surface",
                )
            )
            .group_by(WikiEvidenceMetricEvent.surface)
        )
        level_breakdown_stmt = (
            select(
                WikiEvidenceMetricEvent.level,
                func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0),
            )
            .where(
                and_(
                    *base_filters,
                    WikiEvidenceMetricEvent.event_type == "snippet_open",
                    WikiEvidenceMetricEvent.level.isnot(None),
                )
            )
            .group_by(WikiEvidenceMetricEvent.level)
        )
        quality_outcome_surface_stmt = (
            select(
                WikiEvidenceMetricEvent.surface,
                func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0),
            )
            .where(
                and_(
                    *base_filters,
                    WikiEvidenceMetricEvent.event_type == _QUALITY_OUTCOME_NEGATIVE_EVENT_TYPE,
                )
            )
            .group_by(WikiEvidenceMetricEvent.surface)
        )

        total_events = int((await db.execute(total_events_stmt)).scalar() or 0)
        evidence_surface_count = int((await db.execute(evidence_surface_stmt)).scalar() or 0)
        snippet_open_count = int((await db.execute(snippet_open_stmt)).scalar() or 0)
        dropped_event_count = int((await db.execute(dropped_event_stmt)).scalar() or 0)
        quality_outcome_negative_count = int((await db.execute(quality_outcome_negative_stmt)).scalar() or 0)
        query_count = int((await db.execute(query_count_stmt)).scalar() or 0)
        requery_count = int((await db.execute(requery_stmt)).scalar() or 0)
        deep_verification_count = int((await db.execute(deep_verification_stmt)).scalar() or 0)
        quick_bounce_count = int((await db.execute(quick_bounce_stmt)).scalar() or 0)

        dwell_row = (await db.execute(dwell_stmt)).one()
        total_dwell_ms = int(dwell_row[0] or 0)
        dwell_samples = int(dwell_row[1] or 0)
        avg_dwell_ms = round(total_dwell_ms / dwell_samples, 2) if dwell_samples > 0 else 0.0

        snippet_open_by_surface: dict[str, int] = {surface: 0 for surface in _SURFACES}
        for surface, count in (await db.execute(surface_breakdown_stmt)).all():
            snippet_open_by_surface[str(surface)] = int(count or 0)
        evidence_surface_by_surface: dict[str, int] = {surface: 0 for surface in _SURFACES}
        for surface, count in (await db.execute(evidence_surface_breakdown_stmt)).all():
            evidence_surface_by_surface[str(surface)] = int(count or 0)

        snippet_open_by_level: dict[str, int] = {level: 0 for level in _LEVELS}
        for level, count in (await db.execute(level_breakdown_stmt)).all():
            if level is None:
                continue
            snippet_open_by_level[str(level)] = int(count or 0)
        quality_outcome_negative_by_surface: dict[str, int] = {surface: 0 for surface in _SURFACES}
        for surface, count in (await db.execute(quality_outcome_surface_stmt)).all():
            quality_outcome_negative_by_surface[str(surface)] = int(count or 0)
        outcome_rate_denominator = sum(
            evidence_surface_by_surface[surface]
            for surface in _SURFACES
            if quality_outcome_negative_by_surface[surface] > 0
        )
        if outcome_rate_denominator <= 0:
            outcome_rate_denominator = evidence_surface_count

        payload = WikiEvidenceSummaryResponse(
            days=days,
            retention_days=_RETENTION_DAYS,
            total_events=total_events,
            evidence_surface_count=evidence_surface_count,
            snippet_open_count=snippet_open_count,
            dropped_event_count=dropped_event_count,
            snippet_expansion_rate=_safe_rate(snippet_open_count, evidence_surface_count),
            deep_verification_count=deep_verification_count,
            deep_verification_rate=_safe_rate(deep_verification_count, snippet_open_count),
            quick_bounce_count=quick_bounce_count,
            quick_bounce_rate=_safe_rate(quick_bounce_count, snippet_open_count),
            quality_outcome_negative_count=quality_outcome_negative_count,
            quality_outcome_negative_rate=_safe_rate(quality_outcome_negative_count, outcome_rate_denominator),
            query_count=query_count,
            requery_count=requery_count,
            requery_rate=_safe_rate(requery_count, query_count),
            verification_dwell_avg_ms=avg_dwell_ms,
            verification_dwell_sample_count=dwell_samples,
            snippet_open_by_surface=snippet_open_by_surface,
            snippet_open_by_level=snippet_open_by_level,
            quality_outcome_negative_by_surface=quality_outcome_negative_by_surface,
        )
        return success_response(data=payload.model_dump())
    except Exception as e:
        raise internal_error(operation="Get wiki evidence summary", exception=e) from e


def _reset_wiki_evidence_alert_state_for_test() -> None:
    global _last_cleanup_at
    _last_cleanup_at = None
    reset_wiki_evidence_alert_state_for_test()
