"""Memory operation ledger service.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryOperationEvent (POS: framework-level memory event DTO)
app.database.models.memory::* (POS: 记忆域 ORM 模型)

[OUTPUT]
MemoryOperationLedgerService: durable memory operation, health snapshot, migration provenance service,
Guardian morning-digest aggregation, and live SSE publish for Command Center.

[POS]
单用户记忆观测账本服务。为 GUI 指挥中心提供可审计事件流、影响证据、健康快照缓存和迁移来源追踪。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import (
    MemoryInfluenceRef,
    MemoryOperationEvent,
    MemoryOperationKind,
    MemoryOperationStatus,
)
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import (
    MemoryHealthSnapshotModel,
    MemoryMigrationProvenanceModel,
    MemoryOperationEventModel,
)
from app.services.memory.guardian_policy import MemoryGuardianPolicy

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]

logger = logging.getLogger(__name__)

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


class MemoryOperationLedgerService:
    """Persists and queries single-user memory observability records."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_event(
        self,
        *,
        kind: MemoryOperationKind,
        status: MemoryOperationStatus = MemoryOperationStatus.SUCCESS,
        summary: str,
        memory_id: str | None = None,
        memory_type: str | None = None,
        namespace: str | None = None,
        source: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        influence_refs: list[MemoryInfluenceRef] | None = None,
        metadata: JsonObject | None = None,
        occurred_at: datetime | None = None,
        commit: bool = False,
    ) -> MemoryOperationEventModel:
        event = MemoryOperationEvent(
            id=uuid4().hex,
            kind=kind,
            status=status,
            occurred_at=occurred_at or datetime.now(UTC),
            memory_id=memory_id,
            memory_type=memory_type,
            namespace=namespace,
            source=source,
            summary=summary,
            target_kind=target_kind,
            target_id=target_id,
            correlation_id=correlation_id,
            influence_refs=influence_refs or [],
            metadata=metadata or {},
        )
        row = self._event_to_model(event)
        self._db.add(row)
        _publish_memory_operation_event(row)
        if commit:
            await self._db.commit()
        return row

    async def list_events(self, *, limit: int = 50) -> list[MemoryOperationEventModel]:
        result = await self._db.execute(
            select(MemoryOperationEventModel).order_by(desc(MemoryOperationEventModel.occurred_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def list_events_for_session(self, session_id: str, *, limit: int = 48) -> list[MemoryOperationEventModel]:
        from sqlalchemy import or_

        metadata_chat_id = MemoryOperationEventModel.metadata_json["chat_id"].as_string()
        result = await self._db.execute(
            select(MemoryOperationEventModel)
            .where(
                or_(
                    MemoryOperationEventModel.target_id == session_id,
                    metadata_chat_id == session_id,
                )
            )
            .order_by(MemoryOperationEventModel.occurred_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_events_since(self, since: datetime) -> int:
        result = await self._db.execute(
            select(func.count()).select_from(MemoryOperationEventModel).where(MemoryOperationEventModel.occurred_at >= since)
        )
        return int(result.scalar_one() or 0)

    async def latest_guardian_morning_digest(
        self,
        *,
        policy: MemoryGuardianPolicy | None = None,
    ) -> dict[str, object]:
        """Return a compact digest aggregated over the latest completed maintenance window."""
        window_start, window_end, window_mode = _resolve_guardian_digest_window(policy=policy)
        event_result = await self._db.execute(
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
            counts["forgotten"] += _coerce_int(metadata.get("forgotten_count"))
            counts["archived"] += _coerce_int(metadata.get("archived_count"))
            counts["merged"] += _coerce_int(metadata.get("merged_count"))
            counts["corrected"] += _coerce_int(metadata.get("corrected_count"))
            counts["stale_removed"] += _coerce_int(metadata.get("staleness_removed"))
            counts["stale_extended"] += _coerce_int(metadata.get("staleness_extended"))
            duration_ms_total += _coerce_int(metadata.get("duration_ms"))
            if bool(metadata.get("forced", False)):
                forced_runs += 1

        latest_event = events[0]
        latest_snapshot, health_delta = await self._resolve_window_health_delta(
            window_start=window_start,
            window_end=window_end,
        )
        event_count = len(events)
        return {
            "available": True,
            "occurred_at": _as_aware(latest_event.occurred_at).isoformat(),
            "summary": _build_guardian_digest_summary(
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
        self,
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
        result = await self._db.execute(
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
                latest_occurred_at = _as_aware(row.occurred_at)

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

    async def _resolve_window_health_delta(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[MemoryHealthSnapshotModel | None, int | None]:
        snapshot_result = await self._db.execute(
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
            previous_result = await self._db.execute(
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

    async def latest_health_snapshot(self) -> MemoryHealthSnapshotModel | None:
        result = await self._db.execute(
            select(MemoryHealthSnapshotModel).order_by(desc(MemoryHealthSnapshotModel.checked_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_fresh_health_snapshot(self, *, ttl_seconds: int) -> MemoryHealthSnapshotModel | None:
        snapshot = await self.latest_health_snapshot()
        if snapshot is None:
            return None
        checked_at = _as_aware(snapshot.checked_at)
        if datetime.now(UTC) - checked_at > timedelta(seconds=ttl_seconds):
            return None
        return snapshot

    async def save_health_snapshot(
        self,
        *,
        status: str,
        total: int | None,
        dimensions: dict[str, float],
        suggestions: list[str],
        has_graph: bool,
        sample_size: int,
        guardian_running: bool,
        seconds_until_next: int | None,
        ttl_seconds: int,
        commit: bool = False,
    ) -> MemoryHealthSnapshotModel:
        row = MemoryHealthSnapshotModel(
            id=uuid4().hex,
            status=status,
            total=total,
            dimensions_json=dimensions,
            suggestions_json=suggestions,
            has_graph=has_graph,
            sample_size=sample_size,
            guardian_running=guardian_running,
            seconds_until_next=seconds_until_next,
            checked_at=datetime.now(UTC),
            ttl_seconds=ttl_seconds,
            metadata_json={"source": "memory_command_center"},
        )
        self._db.add(row)
        if commit:
            await self._db.commit()
        return row

    async def record_migration(
        self,
        *,
        source: str,
        status: str,
        imported_count: int,
        unmapped_count: int,
        metadata: dict[str, object] | None = None,
        commit: bool = False,
    ) -> MemoryMigrationProvenanceModel:
        now = datetime.now(UTC)
        row = MemoryMigrationProvenanceModel(
            id=uuid4().hex,
            source=source,
            status=status,
            imported_count=imported_count,
            unmapped_count=unmapped_count,
            started_at=now,
            completed_at=now,
            metadata_json=metadata,
        )
        self._db.add(row)
        if commit:
            await self._db.commit()
        return row

    async def migration_summary(self) -> tuple[int, int, str]:
        result = await self._db.execute(select(MemoryMigrationProvenanceModel))
        rows = list(result.scalars().all())
        if not rows:
            return (0, 0, "not_tracked")
        tracked = sum(row.imported_count for row in rows)
        unmapped = sum(row.unmapped_count for row in rows)
        coverage = "complete" if unmapped == 0 else "partial"
        return (tracked, unmapped, coverage)

    async def latest_migration(self) -> MemoryMigrationProvenanceModel | None:
        result = await self._db.execute(
            select(MemoryMigrationProvenanceModel).order_by(desc(MemoryMigrationProvenanceModel.completed_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def update_migration_metadata_by_batch(
        self,
        *,
        import_batch_id: str,
        metadata: dict[str, object],
    ) -> None:
        """Merge metadata into the latest migration provenance row for an import batch."""

        result = await self._db.execute(
            select(MemoryMigrationProvenanceModel)
            .where(MemoryMigrationProvenanceModel.metadata_json["import_batch_id"].as_string() == import_batch_id)
            .order_by(desc(MemoryMigrationProvenanceModel.completed_at))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        row.metadata_json = {**(row.metadata_json or {}), **metadata}

    @staticmethod
    def model_to_event(row: MemoryOperationEventModel) -> MemoryOperationEvent:
        return MemoryOperationEvent(
            id=row.id,
            kind=MemoryOperationKind(row.kind),
            status=MemoryOperationStatus(row.status),
            occurred_at=_as_aware(row.occurred_at),
            memory_id=row.memory_id,
            memory_type=row.memory_type,
            namespace=row.namespace,
            source=row.source,
            summary=row.summary,
            target_kind=row.target_kind,
            target_id=row.target_id,
            correlation_id=row.correlation_id,
            influence_refs=[MemoryInfluenceRef(**ref) for ref in row.influence_refs_json or []],
            metadata=_coerce_metadata(row.metadata_json),
        )

    @staticmethod
    def _event_to_model(event: MemoryOperationEvent) -> MemoryOperationEventModel:
        return MemoryOperationEventModel(
            id=event.id,
            kind=event.kind.value,
            status=event.status.value,
            occurred_at=event.occurred_at,
            memory_id=event.memory_id,
            memory_type=event.memory_type,
            namespace=event.namespace,
            source=event.source,
            summary=event.summary,
            target_kind=event.target_kind,
            target_id=event.target_id,
            correlation_id=event.correlation_id,
            influence_refs_json=[ref.model_dump(mode="json") for ref in event.influence_refs],
            metadata_json=event.metadata,
        )


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _resolve_guardian_digest_window(
    *,
    policy: MemoryGuardianPolicy | None,
    now_utc: datetime | None = None,
) -> tuple[datetime, datetime, str]:
    resolved_now = _as_aware(now_utc or datetime.now(UTC))
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


def _build_guardian_digest_summary(*, event_count: int, counts: dict[str, int], window_mode: str) -> str:
    title = "Guardian night cleanup" if window_mode == "quiet_window" else "Guardian cleanup (last 24h)"
    return (
        f"{title}: "
        f"{event_count} run(s), "
        f"merged {counts['merged']}, corrected {counts['corrected']}, "
        f"archived {counts['archived']}, forgotten {counts['forgotten']}."
    )


def _timeline_payload_from_model(row: MemoryOperationEventModel) -> dict[str, object]:
    """Serialize one ledger row for Command Center live stream SSE."""
    event = MemoryOperationLedgerService.model_to_event(row)
    return {
        "id": event.id,
        "kind": event.kind.value,
        "status": event.status.value,
        "occurred_at": event.occurred_at.isoformat(),
        "title": event.memory_type or event.kind.value,
        "description": event.summary,
        "source": event.source or "memory_operation_ledger",
        "memory_type": event.memory_type,
        "namespace": event.namespace,
        "target_kind": event.target_kind,
        "target_id": event.target_id,
        "influence_count": len(event.influence_refs),
        "metadata": event.metadata,
    }


def _publish_memory_operation_event(row: MemoryOperationEventModel) -> None:
    """Push one memory operation to connected SSE clients."""
    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.MEMORY_OPERATION,
                data=_timeline_payload_from_model(row),
            )
        )
    except Exception as exc:
        logger.warning("Failed to publish memory_operation SSE event %s: %s", row.id, exc)


def _coerce_metadata(value: dict[str, object] | None) -> JsonObject:
    if not value:
        return {}
    result: JsonObject = {}
    for key, raw in value.items():
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            result[str(key)] = raw
    return result


def _coerce_int(value: object) -> int:
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
