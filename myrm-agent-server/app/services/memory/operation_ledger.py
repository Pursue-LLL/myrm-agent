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
from app.services.memory.operation_ledger_guardian import (
    _resolve_guardian_digest_window,
    as_aware,
    guardian_guard_alert_thresholds,
)
from app.services.memory.operation_ledger_guardian import (
    guardian_guard_alert_snapshot as build_guardian_guard_alert_snapshot,
)
from app.services.memory.operation_ledger_guardian import (
    latest_guardian_morning_digest as build_latest_guardian_morning_digest,
)

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]

logger = logging.getLogger(__name__)


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
        return await build_latest_guardian_morning_digest(self._db, policy=policy)

    async def guardian_guard_alert_snapshot(
        self,
        *,
        lookback_hours: int = 24,
        frequency_tier: str | None = None,
    ) -> dict[str, object]:
        return await build_guardian_guard_alert_snapshot(
            self._db,
            lookback_hours=lookback_hours,
            frequency_tier=frequency_tier,
        )

    async def latest_health_snapshot(self) -> MemoryHealthSnapshotModel | None:
        result = await self._db.execute(
            select(MemoryHealthSnapshotModel).order_by(desc(MemoryHealthSnapshotModel.checked_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_fresh_health_snapshot(self, *, ttl_seconds: int) -> MemoryHealthSnapshotModel | None:
        snapshot = await self.latest_health_snapshot()
        if snapshot is None:
            return None
        checked_at = as_aware(snapshot.checked_at)
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
            occurred_at=as_aware(row.occurred_at),
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


__all__ = [
    "MemoryOperationLedgerService",
    "guardian_guard_alert_thresholds",
    "_resolve_guardian_digest_window",
]
