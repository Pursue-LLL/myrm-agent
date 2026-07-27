"""Wiki evidence governance alert helpers.

[INPUT]
- app.database.models::WikiEvidenceMetricEvent (POS: observability event ORM model)
- app.database.models::SystemNotification (POS: persisted async notification model)
- app.services.infra.system_notification::SystemNotificationService (POS: notification write service)

[OUTPUT]
- maybe_emit_governance_alerts: emit quality alerts with cooldown protection.
- reset_wiki_evidence_alert_state_for_test: test-only in-memory state reset.

[POS]
Centralizes governance alert query/emit logic so API route files stay focused on
request/response handling and remain within line-budget constraints.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SystemNotification, WikiEvidenceMetricEvent
from app.services.infra.system_notification import SystemNotificationService

_ALERT_WINDOW_DAYS = 7
_ALERT_COOLDOWN = timedelta(hours=6)
_ALERT_DROPPED_EVENT_THRESHOLD = 10
_ALERT_DEEP_VERIFICATION_MIN_OPEN_COUNT = 10
_ALERT_DEEP_VERIFICATION_MIN_DWELL_SAMPLES = 5
_ALERT_DEEP_VERIFICATION_RATE_THRESHOLD = 0.2
_ALERT_ACTION_URL = "/settings/developer?sub=usage"
_DEEP_VERIFICATION_THRESHOLD_MS = 8_000

_alert_emit_lock = asyncio.Lock()
_last_alert_emitted_at_by_key: dict[str, float] = {}


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _is_alert_in_cooldown(alert_key: str, now_ts: float) -> bool:
    last_emitted_at = _last_alert_emitted_at_by_key.get(alert_key)
    if last_emitted_at is None:
        return False
    return now_ts - last_emitted_at < _ALERT_COOLDOWN.total_seconds()


def _mark_alert_emitted(alert_key: str, now_ts: float) -> None:
    _last_alert_emitted_at_by_key[alert_key] = now_ts


async def _collect_governance_alert_candidates(
    db: AsyncSession, now: datetime
) -> list[dict[str, object]]:
    start_dt = now - timedelta(days=_ALERT_WINDOW_DAYS)
    base_filters = (WikiEvidenceMetricEvent.created_at >= start_dt,)

    dropped_event_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
        and_(
            *base_filters,
            WikiEvidenceMetricEvent.event_type == "dropped_report",
        )
    )
    snippet_open_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
        and_(
            *base_filters,
            WikiEvidenceMetricEvent.event_type == "snippet_open",
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
    dwell_samples_stmt = select(func.coalesce(func.sum(WikiEvidenceMetricEvent.count), 0)).where(
        and_(
            *base_filters,
            WikiEvidenceMetricEvent.event_type == "snippet_close",
            WikiEvidenceMetricEvent.dwell_ms.isnot(None),
        )
    )

    dropped_event_count = int((await db.execute(dropped_event_stmt)).scalar() or 0)
    snippet_open_count = int((await db.execute(snippet_open_stmt)).scalar() or 0)
    deep_verification_count = int((await db.execute(deep_verification_stmt)).scalar() or 0)
    dwell_samples = int((await db.execute(dwell_samples_stmt)).scalar() or 0)
    deep_verification_rate = _safe_rate(deep_verification_count, snippet_open_count)

    alerts: list[dict[str, object]] = []
    if dropped_event_count >= _ALERT_DROPPED_EVENT_THRESHOLD:
        alerts.append(
            {
                "alert_key": "wiki_evidence_dropped_events",
                "title": "Knowledge Evidence Telemetry Drops Detected",
                "message": (
                    f"Wiki evidence telemetry dropped {dropped_event_count} events in the last "
                    f"{_ALERT_WINDOW_DAYS} days. Check client connectivity and queue health."
                ),
                "type": "warning",
                "meta_data": {
                    "kind": "wiki_evidence_governance_alert",
                    "alert_key": "wiki_evidence_dropped_events",
                    "window_days": _ALERT_WINDOW_DAYS,
                    "dropped_event_count": dropped_event_count,
                    "action_url": _ALERT_ACTION_URL,
                },
            }
        )

    if (
        snippet_open_count >= _ALERT_DEEP_VERIFICATION_MIN_OPEN_COUNT
        and dwell_samples >= _ALERT_DEEP_VERIFICATION_MIN_DWELL_SAMPLES
        and deep_verification_rate < _ALERT_DEEP_VERIFICATION_RATE_THRESHOLD
    ):
        alerts.append(
            {
                "alert_key": "wiki_evidence_low_deep_verification",
                "title": "Knowledge Evidence Verification Quality Is Low",
                "message": (
                    f"Wiki evidence deep verification rate is {deep_verification_rate * 100:.1f}% "
                    f"(opens={snippet_open_count}, deep={deep_verification_count}) over the last "
                    f"{_ALERT_WINDOW_DAYS} days."
                ),
                "type": "warning",
                "meta_data": {
                    "kind": "wiki_evidence_governance_alert",
                    "alert_key": "wiki_evidence_low_deep_verification",
                    "window_days": _ALERT_WINDOW_DAYS,
                    "snippet_open_count": snippet_open_count,
                    "deep_verification_count": deep_verification_count,
                    "deep_verification_rate": deep_verification_rate,
                    "action_url": _ALERT_ACTION_URL,
                },
            }
        )

    return alerts


async def _load_recent_alert_keys(db: AsyncSession, now: datetime) -> set[str]:
    cutoff = now - _ALERT_COOLDOWN
    stmt = (
        select(SystemNotification.meta_data)
        .where(
            and_(
                SystemNotification.source == "wiki_evidence",
                SystemNotification.created_at >= cutoff,
            )
        )
        .order_by(SystemNotification.created_at.desc())
        .limit(100)
    )
    keys: set[str] = set()
    rows = (await db.execute(stmt)).scalars().all()
    for meta_data in rows:
        if not isinstance(meta_data, dict):
            continue
        alert_key = meta_data.get("alert_key")
        if isinstance(alert_key, str):
            keys.add(alert_key)
    return keys


async def maybe_emit_governance_alerts(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    now_ts = time.time()
    async with _alert_emit_lock:
        alert_candidates = await _collect_governance_alert_candidates(db, now)
        recent_alert_keys = await _load_recent_alert_keys(db, now)
        emitted = 0
        emitted_keys: list[str] = []
        for alert in alert_candidates:
            alert_key = str(alert["alert_key"])
            if _is_alert_in_cooldown(alert_key, now_ts) or alert_key in recent_alert_keys:
                continue
            notif_id = await SystemNotificationService.create_notification(
                title=str(alert["title"]),
                message=str(alert["message"]),
                type=str(alert["type"]),
                source="wiki_evidence",
                meta_data=alert.get("meta_data") if isinstance(alert.get("meta_data"), dict) else None,
                session=db,
            )
            if notif_id:
                recent_alert_keys.add(alert_key)
                emitted_keys.append(alert_key)
                emitted += 1
        if emitted > 0:
            await db.commit()
            for alert_key in emitted_keys:
                _mark_alert_emitted(alert_key, now_ts)
        return emitted


def reset_wiki_evidence_alert_state_for_test() -> None:
    _last_alert_emitted_at_by_key.clear()
