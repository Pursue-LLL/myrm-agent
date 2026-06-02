"""Personal memory command center aggregation service.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.database.models.memory::PendingMemory (POS: 记忆域模型)
app.database.models.memory::SharedContextModel (POS: 记忆域模型)

[OUTPUT]
MemoryCommandCenterService: builds the single-user memory command center snapshot.

[POS]
个人大脑指挥中心聚合服务。基于 MemoryManager、记忆治理 ORM 和部署设置生成设置页可观测快照。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
    MemorySpaceKind,
    MemoryType,
)
from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.deploy_mode import get_deploy_mode, get_embedding_mode, get_storage_mode
from app.config.settings import settings
from app.database.models.memory import (
    MemoryOperationEventModel,
    PendingMemory,
    SharedContextBindingModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.schemas.memory.command_center import (
    MemoryCommandCenterResponse,
    MemoryCommandGovernanceItem,
    MemoryCommandHealth,
    MemoryCommandOverview,
    MemoryCommandRuntimeStatus,
    MemoryCommandSpace,
    MemoryCommandTimelineEvent,
    MemoryCommandTraceRun,
    MemoryCommandTraceStep,
)
from app.services.memory.archive_restore import MemoryArchiveRestoreService
from app.services.memory.command_center_insights import MemoryCommandCenterInsights
from app.services.memory.diagnostics import MemoryDiagnosticsService
from app.services.memory.import_ledger import MemoryImportLedgerService
from app.services.memory.operation_ledger import MemoryOperationLedgerService

logger = logging.getLogger(__name__)
HEALTH_TTL_SECONDS = 300
TRACE_RUN_LIMIT = 6
TRACE_STEP_LIMIT = 16
TRACE_SOURCE = "memory_retrieval_trace"
TRACE_STATUSES = {"success", "warning", "error", "skipped"}

ALL_MEMORY_TYPES: tuple[MemoryType, ...] = (
    MemoryType.PROFILE,
    MemoryType.SEMANTIC,
    MemoryType.EPISODIC,
    MemoryType.PROCEDURAL,
    MemoryType.CONVERSATION,
    MemoryType.CLAIM,
    MemoryType.TASK_DIGEST,
)


class MemoryCommandCenterService:
    """Builds the single-user memory command center snapshot."""

    def __init__(self, db: AsyncSession, memory_manager: MemoryManager) -> None:
        self._db = db
        self._memory_manager = memory_manager
        self._ledger = MemoryOperationLedgerService(db)
        self._import_ledger = MemoryImportLedgerService(db)
        self._insights = MemoryCommandCenterInsights(db, memory_manager, self._ledger)
        self._diagnostics = MemoryDiagnosticsService(db, memory_manager, ledger=self._ledger)

    async def build_snapshot(self) -> MemoryCommandCenterResponse:
        generated_at = datetime.now(UTC)
        by_type = await self._count_memories_by_type()
        pending_memories = await self._count_rows(
            select(func.count()).select_from(PendingMemory).where(PendingMemory.status == "pending")
        )
        pending_shared_proposals = await self._count_rows(
            select(func.count())
            .select_from(SharedContextWriteProposalModel)
            .where(SharedContextWriteProposalModel.status == "pending")
        )
        active_shared_contexts = await self._count_rows(
            select(func.count()).select_from(SharedContextModel).where(SharedContextModel.status == "active")
        )
        health = await self._build_health()
        deploy_mode = get_deploy_mode().value
        timeline = await self._build_timeline()
        influence = await self._insights.build_influence()
        cost = await self._insights.build_cost_profile(influence)
        governance = await self._build_governance()
        conflicts = await self._insights.build_conflicts()
        migration = await self._insights.build_migration()
        import_rollback_health = await self._import_ledger.rollback_health()
        archive_restore_health = await MemoryArchiveRestoreService(self._db).restore_health()
        runtime = self._build_runtime(deploy_mode)

        overview = MemoryCommandOverview(
            total_memories=sum(by_type.values()),
            by_type=by_type,
            pending_memories=pending_memories,
            pending_shared_proposals=pending_shared_proposals,
            active_shared_contexts=active_shared_contexts,
            health_score=health.total,
            health_status=health.status,
            deploy_mode=deploy_mode,
        )

        return MemoryCommandCenterResponse(
            generated_at=generated_at,
            overview=overview,
            spaces=await self._build_spaces(),
            governance=governance,
            health=health,
            timeline=timeline,
            live_stream=timeline[:12],
            influence=influence,
            cost=cost,
            conflicts=conflicts,
            replay=await self._insights.build_replay(timeline, influence),
            replay_events=self._insights.build_replay_events(timeline),
            waterfall=self._insights.build_waterfall(timeline, influence, cost),
            trace_runs=self._build_trace_runs(timeline),
            eval_metrics=self._insights.build_eval_metrics(
                timeline=timeline,
                influence=influence,
                conflicts=conflicts,
                migration=migration,
            ),
            connectors=self._insights.build_connectors(),
            privacy=self._insights.build_privacy_signals(timeline),
            doctor_checks=await self._diagnostics.build_doctor_checks(
                health_cache_status=health.cache_status,
                runtime=runtime,
            ),
            migration=migration,
            plane_summary=self._insights.build_plane_summary(
                health_status=health.status,
                storage_mode=get_storage_mode().value,
                timeline=timeline,
                governance_backlog=len(governance),
                import_rollback_health=import_rollback_health,
                archive_restore_health=archive_restore_health,
            ),
            runtime=runtime,
        )

    def _build_trace_runs(self, timeline: list[MemoryCommandTimelineEvent]) -> list[MemoryCommandTraceRun]:
        grouped: dict[str, list[MemoryCommandTimelineEvent]] = {}
        for event in timeline:
            if event.source != TRACE_SOURCE:
                continue
            trace_id = _metadata_str(event.metadata, "trace_id") or event.id
            grouped.setdefault(trace_id, []).append(event)

        ordered_groups = sorted(
            grouped.items(),
            key=lambda item: max(event.occurred_at for event in item[1]),
            reverse=True,
        )
        return [
            self._timeline_events_to_trace_run(trace_id, events)
            for trace_id, events in ordered_groups[:TRACE_RUN_LIMIT]
        ]

    @staticmethod
    def _timeline_events_to_trace_run(
        trace_id: str,
        events: list[MemoryCommandTimelineEvent],
    ) -> MemoryCommandTraceRun:
        ordered_events = sorted(events, key=_trace_step_sort_key)
        steps = [
            MemoryCommandTraceStep(
                id=event.id,
                phase=_metadata_str(event.metadata, "step_phase") or event.kind,
                status=_trace_status(event.status),
                title=_metadata_str(event.metadata, "step_title") or event.title,
                description=event.description,
                occurred_at=event.occurred_at,
                duration_ms=_metadata_float(event.metadata, "duration_ms"),
                output_count=_metadata_int(event.metadata, "output_count") or 0,
                result_count=_metadata_int(event.metadata, "result_count") or 0,
                step_index=_metadata_int(event.metadata, "step_index") or index,
            )
            for index, event in enumerate(ordered_events[:TRACE_STEP_LIMIT])
        ]
        return MemoryCommandTraceRun(
            id=f"trace-run:{trace_id}",
            trace_id=trace_id,
            message_id=_first_metadata_str(ordered_events, "message_id"),
            chat_id=_first_metadata_str(ordered_events, "chat_id"),
            query_preview=_first_metadata_str(ordered_events, "query_preview") or "",
            status=_trace_run_status(ordered_events),
            occurred_at=max(event.occurred_at for event in ordered_events),
            duration_ms=_trace_run_duration_ms(ordered_events),
            result_count=max((_metadata_int(event.metadata, "result_count") or 0) for event in ordered_events),
            steps=steps,
        )

    async def _count_memories_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for memory_type in ALL_MEMORY_TYPES:
            try:
                counts[memory_type.value] = await self._memory_manager.count_memories(memory_type)
            except Exception as exc:
                logger.warning("Memory count failed for %s: %s", memory_type.value, exc)
                counts[memory_type.value] = 0
        return counts

    async def _build_spaces(self) -> list[MemoryCommandSpace]:
        spaces: list[MemoryCommandSpace] = [
            MemoryCommandSpace(
                namespace=namespace,
                kind=self._space_kind(namespace).value,
                label=self._space_label(namespace),
                active=True,
            )
            for namespace in self._memory_manager.namespaces
        ]

        binding_counts = await self._shared_context_binding_counts()
        result = await self._db.execute(select(SharedContextModel).order_by(desc(SharedContextModel.updated_at)).limit(20))
        for context in result.scalars().all():
            spaces.append(
                MemoryCommandSpace(
                    namespace=context.namespace,
                    kind=MemorySpaceKind.SHARED.value,
                    label=context.name,
                    context_id=context.id,
                    active=context.status == "active",
                    binding_count=binding_counts.get(context.id, 0),
                )
            )
        return spaces

    async def _build_governance(self) -> list[MemoryCommandGovernanceItem]:
        items: list[MemoryCommandGovernanceItem] = []

        pending_result = await self._db.execute(
            select(PendingMemory).where(PendingMemory.status == "pending").order_by(desc(PendingMemory.created_at)).limit(5)
        )
        for item in pending_result.scalars().all():
            items.append(
                MemoryCommandGovernanceItem(
                    id=item.id,
                    kind=MemoryOperationKind.PROPOSE.value,
                    target_kind="pending_memory",
                    title=item.memory_type,
                    description=self._preview(item.content),
                    severity="warning",
                    status=item.status,
                    created_at=item.created_at,
                    available_actions=["approve", "reject", "edit"],
                )
            )

        proposal_result = await self._db.execute(
            select(SharedContextWriteProposalModel)
            .where(SharedContextWriteProposalModel.status == "pending")
            .order_by(desc(SharedContextWriteProposalModel.created_at))
            .limit(5)
        )
        for proposal in proposal_result.scalars().all():
            items.append(
                MemoryCommandGovernanceItem(
                    id=proposal.id,
                    kind="shared_context_proposal",
                    target_kind="shared_context_proposal",
                    title=proposal.memory_type,
                    description=self._preview(proposal.content),
                    severity="warning",
                    status=proposal.status,
                    created_at=proposal.created_at,
                    available_actions=["approve", "reject", "edit"],
                )
            )

        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:8]

    async def refresh_health(self) -> MemoryCommandHealth:
        return await self._build_health(force_refresh=True)

    async def _build_health(self, *, force_refresh: bool = False) -> MemoryCommandHealth:
        cached = await self._ledger.get_fresh_health_snapshot(ttl_seconds=HEALTH_TTL_SECONDS)
        if cached is not None and not force_refresh:
            return MemoryCommandHealth(
                status=self._health_status(cached.total),
                total=cached.total,
                dimensions=cached.dimensions_json,
                suggestions=cached.suggestions_json,
                has_graph=cached.has_graph,
                sample_size=cached.sample_size,
                guardian_running=cached.guardian_running,
                seconds_until_next=cached.seconds_until_next,
                checked_at=cached.checked_at,
                cache_status="fresh",
            )

        total: int | None = None
        dimensions: dict[str, float] = {}
        suggestions: list[str] = []
        has_graph = self._memory_manager.has_graph
        sample_size = 0

        try:
            health = await self._memory_manager.compute_health_score()
            health_dict = health.to_dict()
            total = int(health_dict.get("total", 0))
            raw_dimensions = health_dict.get("dimensions", {})
            if isinstance(raw_dimensions, dict):
                dimensions = {str(key): float(value) for key, value in raw_dimensions.items() if isinstance(value, (int, float))}
            raw_suggestions = health_dict.get("suggestions", [])
            if isinstance(raw_suggestions, list):
                suggestions = [str(item) for item in raw_suggestions]
            has_graph = bool(health_dict.get("has_graph", has_graph))
            sample_size = int(health_dict.get("sample_size", 0))
        except Exception as exc:
            logger.warning("Memory health snapshot failed: %s", exc)
            total = None

        guardian_running = False
        seconds_until_next: int | None = None
        try:
            from app.lifecycle.memory_guardian import get_memory_guardian_status

            guardian = get_memory_guardian_status()
            guardian_running = bool(guardian.get("running", False))
            raw_next = guardian.get("seconds_until_next")
            if isinstance(raw_next, int):
                seconds_until_next = raw_next
        except Exception as exc:
            logger.warning("Memory guardian status unavailable: %s", exc)
            guardian_running = False

        status = self._health_status(total)
        health = MemoryCommandHealth(
            status=self._health_status(total),
            total=total,
            dimensions=dimensions,
            suggestions=suggestions,
            has_graph=has_graph,
            sample_size=sample_size,
            guardian_running=guardian_running,
            seconds_until_next=seconds_until_next,
            checked_at=datetime.now(UTC),
            cache_status="refreshed",
        )
        await self._ledger.save_health_snapshot(
            status=status,
            total=total,
            dimensions=dimensions,
            suggestions=suggestions,
            has_graph=has_graph,
            sample_size=sample_size,
            guardian_running=guardian_running,
            seconds_until_next=seconds_until_next,
            ttl_seconds=HEALTH_TTL_SECONDS,
        )
        await self._ledger.record_event(
            kind=MemoryOperationKind.HEALTH_CHECK,
            status=MemoryOperationStatus.SUCCESS if total is not None else MemoryOperationStatus.WARNING,
            summary="Memory health snapshot refreshed.",
            source="memory_command_center",
            target_kind="health",
            metadata={"health_score": total, "cache_ttl_seconds": HEALTH_TTL_SECONDS},
        )
        await self._db.commit()
        return health

    async def _build_timeline(self) -> list[MemoryCommandTimelineEvent]:
        ledger_events = await self._ledger.list_events(limit=96)
        if ledger_events:
            return [self._ledger_event_to_timeline(row) for row in ledger_events]

        events: list[MemoryCommandTimelineEvent] = []

        pending_result = await self._db.execute(select(PendingMemory).order_by(desc(PendingMemory.created_at)).limit(6))
        for item in pending_result.scalars().all():
            events.append(
                MemoryCommandTimelineEvent(
                    id=f"pending:{item.id}",
                    kind=MemoryOperationKind.PROPOSE.value,
                    status=item.status,
                    occurred_at=item.created_at,
                    title=item.memory_type,
                    description=self._preview(item.content),
                    source="pending_memory",
                    memory_type=item.memory_type,
                )
            )

        proposal_result = await self._db.execute(
            select(SharedContextWriteProposalModel).order_by(desc(SharedContextWriteProposalModel.created_at)).limit(6)
        )
        for proposal in proposal_result.scalars().all():
            events.append(
                MemoryCommandTimelineEvent(
                    id=f"shared-proposal:{proposal.id}",
                    kind="shared_context_proposal",
                    status=proposal.status,
                    occurred_at=proposal.created_at,
                    title=proposal.memory_type,
                    description=self._preview(proposal.content),
                    source="shared_context_write_proposal",
                    memory_type=proposal.memory_type,
                    namespace=f"shared:{proposal.context_id}",
                )
            )

        context_result = await self._db.execute(select(SharedContextModel).order_by(desc(SharedContextModel.updated_at)).limit(6))
        for context in context_result.scalars().all():
            events.append(
                MemoryCommandTimelineEvent(
                    id=f"shared-context:{context.id}",
                    kind=MemoryOperationKind.WRITE.value,
                    status=context.status,
                    occurred_at=context.updated_at,
                    title=context.name,
                    description=self._preview(context.description or context.namespace),
                    source="shared_context",
                    namespace=context.namespace,
                )
            )

        events.append(
            MemoryCommandTimelineEvent(
                id=f"health:{datetime.now(UTC).isoformat()}",
                kind=MemoryOperationKind.HEALTH_CHECK.value,
                status=MemoryOperationStatus.SUCCESS.value,
                occurred_at=datetime.now(UTC),
                title="memory_health",
                description="Current health score was computed for the visible memory spaces.",
                source="memory_manager",
            )
        )

        events.sort(key=lambda item: item.occurred_at, reverse=True)
        return events[:10]

    def _build_runtime(self, deploy_mode: str) -> MemoryCommandRuntimeStatus:
        return MemoryCommandRuntimeStatus(
            deploy_mode=deploy_mode,
            storage_mode=get_storage_mode().value,
            memory_base_path=settings.database.memory_base_path,
            relational_status="available" if self._memory_manager.has_relational else "unavailable",
            vector_status="available" if self._memory_manager.has_vector else "unavailable",
            graph_status="available" if self._memory_manager.has_graph else "unavailable",
            embedding_status=get_embedding_mode().value if self._memory_manager.has_vector else "unavailable",
            control_plane_status="proxied_by_sandbox"
            if get_deployment_capabilities().is_sandbox_instance
            else "not_used",
            event_ledger_status="available",
            health_snapshot_status="available",
            supported_clients=["local_web", "tauri_desktop", "saas_sandbox"],
        )

    async def _shared_context_binding_counts(self) -> dict[str, int]:
        result = await self._db.execute(
            select(SharedContextBindingModel.context_id, func.count(SharedContextBindingModel.id)).group_by(
                SharedContextBindingModel.context_id
            )
        )
        counts: dict[str, int] = {}
        for context_id, count in result.all():
            counts[str(context_id)] = int(count or 0)
        return counts

    async def _count_rows(self, statement: Select[tuple[int]]) -> int:
        result = await self._db.execute(statement)
        return int(result.scalar_one() or 0)

    @staticmethod
    def _ledger_event_to_timeline(row: MemoryOperationEventModel) -> MemoryCommandTimelineEvent:
        return MemoryCommandTimelineEvent(
            id=row.id,
            kind=row.kind,
            status=row.status,
            occurred_at=row.occurred_at,
            title=row.memory_type or row.kind,
            description=row.summary,
            source=row.source or "memory_operation_ledger",
            memory_type=row.memory_type,
            namespace=row.namespace,
            target_kind=row.target_kind,
            target_id=row.target_id,
            influence_count=len(row.influence_refs_json or []),
            metadata=_coerce_timeline_metadata(row.metadata_json),
        )

    @staticmethod
    def _space_kind(namespace: str) -> MemorySpaceKind:
        prefix = namespace.split(":", 1)[0]
        if prefix == "global":
            return MemorySpaceKind.GLOBAL
        if prefix == "agent":
            return MemorySpaceKind.AGENT
        if prefix == "channel":
            return MemorySpaceKind.CHANNEL
        if prefix == "conversation":
            return MemorySpaceKind.CONVERSATION
        if prefix == "task":
            return MemorySpaceKind.TASK
        if prefix == "shared":
            return MemorySpaceKind.SHARED
        return MemorySpaceKind.UNKNOWN

    @staticmethod
    def _space_label(namespace: str) -> str:
        if ":" not in namespace:
            return namespace
        kind, value = namespace.split(":", 1)
        return f"{kind} / {value}"

    @staticmethod
    def _health_status(score: int | None) -> str:
        if score is None:
            return "unknown"
        if score >= 80:
            return "healthy"
        if score >= 55:
            return "degraded"
        return "critical"

    @staticmethod
    def _preview(content: str, *, limit: int = 160) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: limit - 1]}..."


def _coerce_timeline_metadata(value: dict[str, object] | None) -> dict[str, str | int | float | bool | None]:
    if not value:
        return {}
    result: dict[str, str | int | float | bool | None] = {}
    for key, raw in value.items():
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            result[str(key)] = raw
    return result


def _metadata_str(metadata: dict[str, str | int | float | bool | None], key: str) -> str | None:
    value = metadata.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _metadata_int(metadata: dict[str, str | int | float | bool | None], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _metadata_float(metadata: dict[str, str | int | float | bool | None], key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _first_metadata_str(events: list[MemoryCommandTimelineEvent], key: str) -> str | None:
    for event in events:
        value = _metadata_str(event.metadata, key)
        if value:
            return value
    return None


def _trace_step_sort_key(event: MemoryCommandTimelineEvent) -> tuple[int, datetime]:
    step_index = _metadata_int(event.metadata, "step_index")
    return (step_index if step_index is not None else TRACE_STEP_LIMIT, event.occurred_at)


def _trace_status(status: str) -> str:
    return status if status in TRACE_STATUSES else "warning"


def _trace_run_status(events: list[MemoryCommandTimelineEvent]) -> str:
    statuses = {_trace_status(event.status) for event in events}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    if "success" in statuses:
        return "success"
    return "skipped"


def _trace_run_duration_ms(events: list[MemoryCommandTimelineEvent]) -> float | None:
    durations = [
        duration
        for event in events
        if (duration := _metadata_float(event.metadata, "duration_ms")) is not None
    ]
    if not durations:
        return None
    return max(durations)
