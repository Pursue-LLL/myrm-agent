"""Memory activity timeline for the memory command center.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager, MemoryOperationKind, MemoryOperationStatus (POS: Unified memory manager and ledger enums)
app.database.models.memory::MemoryOperationEventModel, SharedContextModel, SharedContextWriteProposalModel (POS: 记忆域模型)
app.services.memory.command_center.command_center_pending::build_pending_timeline (POS: 审批队列在指挥中心的读取视图)
app.services.memory.command_center.command_center_projection_utils::preview_content, restrict_to_context_ids (POS: 指挥中心投影辅助)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)

[OUTPUT]
build_timeline: ledger-backed timeline, or a derived fallback when the ledger has no events yet.
ledger_event_to_timeline: maps one ledger row to a timeline event.

[POS]
个人大脑指挥中心的活动时间线投影。优先读账本事件（按项目命名空间收窄）；账本为空时回退到待审阅记忆、共享上下文提案与上下文变更推导出的事件。
"""

from __future__ import annotations

from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import (
    MemoryOperationEventModel,
    SharedContextModel,
    SharedContextWriteProposalModel,
)
from app.schemas.memory.command_center import MemoryCommandTimelineEvent
from app.services.memory.command_center.command_center_pending import build_pending_timeline
from app.services.memory.command_center.command_center_projection_utils import (
    preview_content,
    restrict_to_context_ids,
)
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

_LEDGER_EVENT_LIMIT = 96
_FALLBACK_SOURCE_LIMIT = 6
_FALLBACK_EVENT_LIMIT = 10

type TimelineMetadata = dict[str, str | int | float | bool | None]


async def build_timeline(
    *,
    db: AsyncSession,
    ledger: MemoryOperationLedgerService,
    memory_manager: MemoryManager,
    project_context_ids: set[str] | None,
) -> list[MemoryCommandTimelineEvent]:
    ledger_events = await ledger.list_events(limit=_LEDGER_EVENT_LIMIT)
    if ledger_events:
        timeline = [ledger_event_to_timeline(row) for row in ledger_events]
        if project_context_ids is not None:
            project_namespaces = {f"shared:{context_id}" for context_id in project_context_ids}
            timeline = [event for event in timeline if event.namespace in project_namespaces]
        return timeline

    events: list[MemoryCommandTimelineEvent] = []
    if project_context_ids is None:
        events.extend(await build_pending_timeline(memory_manager))
    events.extend(await _proposal_events(db, project_context_ids))
    events.extend(await _context_events(db, project_context_ids))
    if project_context_ids is None:
        now = datetime.now(UTC)
        events.append(
            MemoryCommandTimelineEvent(
                id=f"health:{now.isoformat()}",
                kind=MemoryOperationKind.HEALTH_CHECK.value,
                status=MemoryOperationStatus.SUCCESS.value,
                occurred_at=now,
                title="memory_health",
                description="Current health score was computed for the visible memory spaces.",
                source="memory_manager",
            )
        )
        # The marker is timezone-aware while SQLite rows are naive UTC; align them so the merge sorts instead of raising.
        events = [event.model_copy(update={"occurred_at": _as_utc(event.occurred_at)}) for event in events]

    events.sort(key=lambda item: item.occurred_at, reverse=True)
    return events[:_FALLBACK_EVENT_LIMIT]


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC (the convention of the SQLite-backed ledger and ORM rows)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def _proposal_events(db: AsyncSession, project_context_ids: set[str] | None) -> list[MemoryCommandTimelineEvent]:
    statement = restrict_to_context_ids(
        select(SharedContextWriteProposalModel)
        .order_by(SharedContextWriteProposalModel.created_at.desc())
        .limit(_FALLBACK_SOURCE_LIMIT),
        SharedContextWriteProposalModel.context_id,
        project_context_ids,
    )
    result = await db.execute(statement)
    return [
        MemoryCommandTimelineEvent(
            id=f"shared-proposal:{proposal.id}",
            kind="shared_context_proposal",
            status=proposal.status,
            occurred_at=proposal.created_at,
            title=proposal.memory_type,
            description=preview_content(proposal.content),
            source="shared_context_write_proposal",
            memory_type=proposal.memory_type,
            namespace=f"shared:{proposal.context_id}",
        )
        for proposal in result.scalars().all()
    ]


async def _context_events(db: AsyncSession, project_context_ids: set[str] | None) -> list[MemoryCommandTimelineEvent]:
    statement = restrict_to_context_ids(
        select(SharedContextModel).order_by(SharedContextModel.updated_at.desc()).limit(_FALLBACK_SOURCE_LIMIT),
        SharedContextModel.id,
        project_context_ids,
    )
    result = await db.execute(statement)
    return [
        MemoryCommandTimelineEvent(
            id=f"shared-context:{context.id}",
            kind=MemoryOperationKind.WRITE.value,
            status=context.status,
            occurred_at=context.updated_at,
            title=context.name,
            description=preview_content(context.description or context.namespace),
            source="shared_context",
            namespace=context.namespace,
        )
        for context in result.scalars().all()
    ]


def ledger_event_to_timeline(row: MemoryOperationEventModel) -> MemoryCommandTimelineEvent:
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


def _coerce_timeline_metadata(value: dict[str, object] | None) -> TimelineMetadata:
    if not value:
        return {}
    result: TimelineMetadata = {}
    for key, raw in value.items():
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            result[str(key)] = raw
    return result
