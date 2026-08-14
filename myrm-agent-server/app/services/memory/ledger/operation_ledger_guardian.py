"""Guardian digest and guard-unavailable alert helpers for the memory operation ledger.

[INPUT]
- app.services.memory.guardian_policy::MemoryGuardianPolicy (POS: guardian schedule policy)
- app.database.models.memory::* (POS: memory operation + health snapshot ORM)

[OUTPUT]
- guardian_guard_alert_thresholds / latest_guardian_morning_digest / guardian_guard_alert_snapshot

[POS]
Extracted guardian-specific aggregation from operation_ledger to keep the core ledger module within line budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryHealthSnapshotModel, MemoryOperationEventModel
from app.services.memory.guardian_policy import MemoryGuardianPolicy


@dataclass(frozen=True, slots=True)
class _GuardAlertThresholdProfile:
    min_total_events: int
    escalation_min_reason_count: int
    escalation_min_reason_ratio: float


_DEFAULT_GUARD_ALERT_FREQUENCY_TIER = "balanced"
_GUARD_ALERT_THRESHOLDS_BY_FREQUENCY_TIER: dict[str, _GuardAlertThresholdProfile] = {
    "conservative": _GuardAlertThresholdProfile(
        min_total_events=1,
        escalation_min_reason_count=2,
        escalation_min_reason_ratio=0.75,
    ),
    "balanced": _GuardAlertThresholdProfile(
        min_total_events=2,
        escalation_min_reason_count=2,
        escalation_min_reason_ratio=0.6,
    ),
    "aggressive": _GuardAlertThresholdProfile(
        min_total_events=3,
        escalation_min_reason_count=3,
        escalation_min_reason_ratio=0.7,
    ),
}


def _resolve_guard_alert_threshold_profile(
    *,
    frequency_tier: str | None = None,
) -> _GuardAlertThresholdProfile:
    normalized_tier = (frequency_tier or _DEFAULT_GUARD_ALERT_FREQUENCY_TIER).strip().lower()
    return _GUARD_ALERT_THRESHOLDS_BY_FREQUENCY_TIER.get(
        normalized_tier,
        _GUARD_ALERT_THRESHOLDS_BY_FREQUENCY_TIER[_DEFAULT_GUARD_ALERT_FREQUENCY_TIER],
    )


def guardian_guard_alert_thresholds(*, frequency_tier: str | None = None) -> dict[str, int | float]:
    """Return threshold contract shared by alert query and API fallback."""
    profile = _resolve_guard_alert_threshold_profile(frequency_tier=frequency_tier)
    return {
        "min_total_events": profile.min_total_events,
        "escalation_min_reason_count": profile.escalation_min_reason_count,
        "escalation_min_reason_ratio": profile.escalation_min_reason_ratio,
    }


def as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def resolve_guardian_digest_window(
    *,
    policy: MemoryGuardianPolicy | None,
    now_utc: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    resolved_now = as_aware(now_utc or datetime.now(UTC))
    if policy is None or not policy.quiet_window_enabled:
        return resolved_now - timedelta(hours=24), resolved_now, "rolling_24h"

    offset = timedelta(minutes=policy.timezone_offset_minutes)
    local_now = resolved_now + offset
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_hour = policy.quiet_window_start_hour
    end_hour = policy.quiet_window_end_hour

    local_end = local_midnight + timedelta(hours=end_hour)
    if local_now < local_end:
        local_end -= timedelta(days=1)

    if start_hour < end_hour:
        local_start = local_end.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    else:
        local_start = (local_end - timedelta(days=1)).replace(
            hour=start_hour,
            minute=0,
            second=0,
            microsecond=0,
        )

    return local_start - offset, local_end - offset, "quiet_window"


def build_guardian_digest_summary(*, event_count: int, counts: dict[str, int], window_mode: str) -> str:
    title = "Guardian night cleanup" if window_mode == "quiet_window" else "Guardian cleanup (last 24h)"
    return (
        f"{title}: "
        f"{event_count} run(s), "
        f"merged {counts['merged']}, corrected {counts['corrected']}, "
        f"archived {counts['archived']}, forgotten {counts['forgotten']}."
    )


async def resolve_window_health_delta(
    db: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[MemoryHealthSnapshotModel | None, int | None]:
    snapshot_result = await db.execute(
        select(MemoryHealthSnapshotModel)
        .where(MemoryHealthSnapshotModel.checked_at >= window_start)
        .where(MemoryHealthSnapshotModel.checked_at < window_end)
        .order_by(MemoryHealthSnapshotModel.checked_at)
    )
    snapshots = list(snapshot_result.scalars().all())
    if not snapshots:
        return None, None

    latest_snapshot = snapshots[-1]
    baseline_total: int | None = None
    if len(snapshots) >= 2:
        baseline_total = snapshots[0].total
    else:
        previous_result = await db.execute(
            select(MemoryHealthSnapshotModel)
            .where(MemoryHealthSnapshotModel.checked_at < window_start)
            .order_by(desc(MemoryHealthSnapshotModel.checked_at))
            .limit(1)
        )
        previous_snapshot = previous_result.scalar_one_or_none()
        baseline_total = previous_snapshot.total if previous_snapshot else None

    health_delta = (
        int(latest_snapshot.total) - int(baseline_total)
        if latest_snapshot.total is not None and baseline_total is not None
        else None
    )
    return latest_snapshot, health_delta


async def latest_guardian_morning_digest(
    db: AsyncSession,
    *,
    policy: MemoryGuardianPolicy | None = None,
) -> dict[str, object]:
    """Return a compact digest aggregated over the latest completed maintenance window."""
    window_start, window_end, window_mode = resolve_guardian_digest_window(policy=policy)
    event_result = await db.execute(
        select(MemoryOperationEventModel)
        .where(MemoryOperationEventModel.source == "memory_guardian")
        .where(MemoryOperationEventModel.kind == MemoryOperationKind.MAINTENANCE.value)
        .where(MemoryOperationEventModel.status == MemoryOperationStatus.SUCCESS.value)
        .where(MemoryOperationEventModel.occurred_at >= window_start)
        .where(MemoryOperationEventModel.occurred_at < window_end)
        .order_by(desc(MemoryOperationEventModel.occurred_at))
    )
    events = list(event_result.scalars().all())
    if not events:
        return {
            "available": False,
            "window_started_at": window_start.isoformat(),
            "window_ended_at": window_end.isoformat(),
            "window_mode": window_mode,
        }

    counts = {
        "forgotten": 0,
        "archived": 0,
        "merged": 0,
        "corrected": 0,
        "stale_removed": 0,
        "stale_extended": 0,
    }
    forced_runs = 0
    duration_ms_total = 0
    for event in events:
        metadata = event.metadata_json or {}
        counts["forgotten"] += coerce_int(metadata.get("forgotten_count"))
        counts["archived"] += coerce_int(metadata.get("archived_count"))
        counts["merged"] += coerce_int(metadata.get("merged_count"))
        counts["corrected"] += coerce_int(metadata.get("corrected_count"))
        counts["stale_removed"] += coerce_int(metadata.get("staleness_removed"))
        counts["stale_extended"] += coerce_int(metadata.get("staleness_extended"))
        duration_ms_total += coerce_int(metadata.get("duration_ms"))
        if bool(metadata.get("forced", False)):
            forced_runs += 1

    latest_event = events[0]
    latest_snapshot, health_delta = await resolve_window_health_delta(
        db,
        window_start=window_start,
        window_end=window_end,
    )
    event_count = len(events)
    return {
        "available": True,
        "occurred_at": as_aware(latest_event.occurred_at).isoformat(),
        "summary": build_guardian_digest_summary(
            event_count=event_count,
            counts=counts,
            window_mode=window_mode,
        ),
        "counts": counts,
        "forced": forced_runs > 0,
        "forced_runs": forced_runs,
        "scheduled_runs": event_count - forced_runs,
        "event_count": event_count,
        "duration_ms": duration_ms_total,
        "health_total": latest_snapshot.total if latest_snapshot else None,
        "health_delta": health_delta,
        "health_status": latest_snapshot.status if latest_snapshot else None,
        "next_run_seconds": latest_snapshot.seconds_until_next if latest_snapshot else None,
        "window_started_at": window_start.isoformat(),
        "window_ended_at": window_end.isoformat(),
        "window_mode": window_mode,
    }


async def guardian_guard_alert_snapshot(
    db: AsyncSession,
    *,
    lookback_hours: int = 24,
    frequency_tier: str | None = None,
) -> dict[str, object]:
    """Aggregate recent guard-unavailable warning events for UI alert projection."""
    safe_lookback_hours = max(1, min(168, int(lookback_hours)))
    thresholds = guardian_guard_alert_thresholds(frequency_tier=frequency_tier)
    min_total_events = int(thresholds["min_total_events"])
    escalation_min_reason_count = int(thresholds["escalation_min_reason_count"])
    escalation_min_reason_ratio = float(thresholds["escalation_min_reason_ratio"])
    window_start = datetime.now(UTC) - timedelta(hours=safe_lookback_hours)
    result = await db.execute(
        select(MemoryOperationEventModel)
        .where(MemoryOperationEventModel.source == "memory_guardian")
        .where(MemoryOperationEventModel.kind == MemoryOperationKind.MAINTENANCE.value)
        .where(MemoryOperationEventModel.status == MemoryOperationStatus.WARNING.value)
        .where(MemoryOperationEventModel.occurred_at >= window_start)
        .order_by(desc(MemoryOperationEventModel.occurred_at))
    )
    rows = list(result.scalars().all())
    reason_counts: dict[str, int] = {}
    latest_occurred_at: datetime | None = None
    for row in rows:
        metadata = row.metadata_json or {}
        if metadata.get("operation") != "guard_unavailable_skip":
            continue
        reason_value = metadata.get("reason")
        reason = str(reason_value) if reason_value else "unknown_guard_unavailable"
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if latest_occurred_at is None:
            latest_occurred_at = as_aware(row.occurred_at)

    total = sum(reason_counts.values())
    dominant_reason = max(reason_counts.items(), key=lambda item: item[1])[0] if reason_counts else None
    dominant_reason_count = reason_counts.get(dominant_reason, 0) if dominant_reason else 0
    dominant_reason_ratio = (
        float(dominant_reason_count) / float(total)
        if dominant_reason_count > 0 and total > 0
        else 0.0
    )
    active = total >= min_total_events
    escalated = (
        active
        and dominant_reason_count >= escalation_min_reason_count
        and dominant_reason_ratio >= escalation_min_reason_ratio
    )
    return {
        "active": active,
        "escalated": escalated,
        "window_hours": safe_lookback_hours,
        "total": total,
        "reasons": reason_counts,
        "dominant_reason": dominant_reason,
        "dominant_reason_count": dominant_reason_count,
        "dominant_reason_ratio": dominant_reason_ratio,
        "thresholds": thresholds,
        "last_occurred_at": latest_occurred_at.isoformat() if latest_occurred_at else None,
    }


# Backward-compatible private aliases for tests and monkeypatch hooks.
_resolve_guardian_digest_window = resolve_guardian_digest_window
