"""Memory command center views over the approval queue.

[INPUT]
- myrm_agent_harness.toolkits.memory::{MemoryManager, MemoryOperationKind} (POS: 记忆管理器与审批队列读取)
- myrm_agent_harness.toolkits.memory.types::{PendingRecord, PendingResolutionAction} (POS: 审批队列记录)
- app.database.models.memory::PendingMemory (POS: 仅承载记忆冲突待裁决行)
- app.services.memory.command_center.command_center_projection_utils::preview_content (POS: 预览截断)

[OUTPUT]
- count_pending_review: 待审阅总数（审批队列 + 待裁决冲突）
- build_candidate_records / build_pending_governance / build_pending_timeline: 指挥中心三处待审视图

[POS]
指挥中心读取待审内容的唯一入口。审批队列（harness `pending_records`）是普通提案与隐式纠正提案的唯一事实源；
ORM `pending_memories` 只保存记忆冲突待裁决行，因此仅用于冲突计数与候选列表补充。
队列内容与审批开关无关：推断写入（自动提取）在开关关闭时同样入队，读取视图必须始终展示它们。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind
from myrm_agent_harness.toolkits.memory.types import PendingRecord, PendingResolutionAction
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import PendingMemory
from app.schemas.memory.command_center import (
    MemoryCandidateRecord,
    MemoryCommandGovernanceItem,
    MemoryCommandTimelineEvent,
)
from app.services.memory.command_center.command_center_projection_utils import preview_content

logger = logging.getLogger(__name__)

_DEFAULT_CONFIDENCE = 0.8
_DEFAULT_SOURCE = "extraction"


async def count_pending_review(db: AsyncSession, manager: MemoryManager) -> int:
    """Everything awaiting the user's decision: queued proposals plus unresolved memory conflicts."""
    queued = 0
    try:
        queued = await manager.count_pending()
    except Exception:
        logger.warning("Failed to count the approval queue for the command center", exc_info=True)
    conflicts = await db.execute(
        select(func.count())
        .select_from(PendingMemory)
        .where(PendingMemory.status == "pending", PendingMemory.is_conflict.is_(True))
    )
    return queued + int(conflicts.scalar_one() or 0)


async def build_candidate_records(db: AsyncSession, manager: MemoryManager, *, limit: int = 20) -> list[MemoryCandidateRecord]:
    """Pending candidates for the recall boundary panel: queued proposals first, then open conflicts."""
    candidates = [
        MemoryCandidateRecord(
            id=record.id,
            memory_type=record.memory_type.value,
            content_preview=preview_content(record.content, limit=120),
            confidence=record.confidence if record.confidence is not None else _DEFAULT_CONFIDENCE,
            source=_DEFAULT_SOURCE,
            created_at=record.created_at,
            status="pending",
        )
        for record in await _list_queue(manager, limit)
    ]
    remaining = limit - len(candidates)
    if remaining > 0:
        conflict_rows = await db.execute(
            select(PendingMemory)
            .where(PendingMemory.status == "pending", PendingMemory.is_conflict.is_(True))
            .order_by(PendingMemory.created_at.desc())
            .limit(remaining)
        )
        candidates.extend(
            MemoryCandidateRecord(
                id=row.id,
                memory_type=row.memory_type,
                content_preview=preview_content(row.content, limit=120),
                confidence=float(row.confidence if row.confidence is not None else _DEFAULT_CONFIDENCE),
                source=_DEFAULT_SOURCE,
                created_at=row.created_at,
                status="pending",
            )
            for row in conflict_rows.scalars().all()
        )
    return candidates


async def build_pending_governance(manager: MemoryManager, *, limit: int = 5) -> list[MemoryCommandGovernanceItem]:
    """Actionable queue items; a correction/forget proposal discloses the memory it targets."""
    return [
        MemoryCommandGovernanceItem(
            id=record.id,
            kind=MemoryOperationKind.PROPOSE.value,
            target_kind="pending_memory",
            title=record.memory_type.value,
            description=preview_content(record.content),
            severity="warning",
            status=record.status,
            created_at=record.created_at,
            available_actions=["approve", "reject"],
            existing_value=record.target_content or "",
            candidate_value=("" if record.resolution_action == PendingResolutionAction.DELETE else record.content),
            confidence=record.confidence,
        )
        for record in await _list_queue(manager, limit)
    ]


async def build_pending_timeline(manager: MemoryManager, *, limit: int = 6) -> list[MemoryCommandTimelineEvent]:
    """Timeline fallback used while the operation ledger is still empty."""
    return [
        MemoryCommandTimelineEvent(
            id=f"pending:{record.id}",
            kind=MemoryOperationKind.PROPOSE.value,
            status=record.status,
            occurred_at=record.created_at,
            title=record.memory_type.value,
            description=preview_content(record.content),
            source="pending_memory",
            memory_type=record.memory_type.value,
        )
        for record in await _list_queue(manager, limit)
    ]


async def _list_queue(manager: MemoryManager, limit: int) -> list[PendingRecord]:
    try:
        return await manager.list_pending(limit=limit)
    except Exception:
        logger.warning("Failed to read the approval queue for the command center", exc_info=True)
        return []
