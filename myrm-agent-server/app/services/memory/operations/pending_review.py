"""Pending memory review: approve or reject queued proposals and record the audit trail.

[INPUT]
- myrm_agent_harness.toolkits.memory::{MemoryManager, MemoryNotFoundError, MemoryOperationKind, MemoryOperationStatus, PendingTargetChangedError} (POS: 记忆管理器与操作账本枚举)
- myrm_agent_harness.toolkits.memory.types::{PendingRecord, PendingResolutionAction} (POS: 审批队列记录)
- app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)
- app.services.skills.experience_ledger::{record_experience_event} (POS: 学习资产事件账本)

[OUTPUT]
- PendingReviewSource: 审批入口来源（写入操作账本 source 字段）
- approve_pending / reject_pending: 单条审批动作 + 审计，返回是否真正生效
- batch_approve_pending / batch_reject_pending: 逐条走单条审批路径的批量版本
- record_pending_event: 向操作账本追加审批类事件（冲突仲裁复用）

[POS]
审批队列（harness `pending_records`）的唯一业务审批入口。Web、指挥中心与 IM 三处都经此函数批准/拒绝，
保证每一次生效的审批（含「批准后把旧记忆移入回收站」）都有经验账本与操作账本记录。
同一提案的审批按 pending_id 进程内串行：多个入口（可能持有不同 MemoryManager 实例）同时处理同一条时，
后到者读到已处理状态即为 no-op，既不重复应用也不重复审计。
审计为尽力而为：账本写入失败只记录 WARNING，不会让已生效的审批返回错误。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from enum import StrEnum
from weakref import WeakValueDictionary

from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryNotFoundError,
    MemoryOperationKind,
    MemoryOperationStatus,
    PendingTargetChangedError,
)
from myrm_agent_harness.toolkits.memory.types import PendingRecord, PendingResolutionAction

from app.database.connection import get_session
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

logger = logging.getLogger(__name__)


class PendingReviewSource(StrEnum):
    """Surface that resolved the proposal; stored as the operation ledger ``source``."""

    WEB_API = "memory_pending_api"
    COMMAND_CENTER = "memory_command_center"
    CHANNEL = "memory_channel_command"


_APPROVED_SUFFIX: dict[PendingResolutionAction, str] = {
    PendingResolutionAction.CORRECT: " The target memory was replaced.",
    PendingResolutionAction.DELETE: " The target memory was moved to trash.",
}


_review_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


@asynccontextmanager
async def _exclusive(pending_id: str) -> AsyncIterator[None]:
    """Serialize reviews of one proposal; the registry only keeps locks that are in use."""
    lock = _review_locks.get(pending_id)
    if lock is None:
        lock = _review_locks[pending_id] = asyncio.Lock()
    async with lock:
        yield


async def approve_pending(
    manager: MemoryManager,
    pending_id: str,
    *,
    source: PendingReviewSource,
    edited_content: str | None = None,
    batch: bool = False,
) -> bool:
    """Approve one queued proposal; returns ``False`` when it was already resolved (no-op).

    Raises the harness error (e.g. ``MemoryNotFoundError``) when the approval fails.
    """
    async with _exclusive(pending_id):
        record = await _get_unresolved(manager, pending_id)
        await manager.approve(pending_id, edited_content=edited_content)
        if record is None:
            return False
        await _audit(record, approved=True, source=source, batch=batch, edited=edited_content is not None)
        return True


async def reject_pending(manager: MemoryManager, pending_id: str, *, source: PendingReviewSource, batch: bool = False) -> bool:
    """Reject one queued proposal; returns ``False`` when it was already resolved (no-op).

    Raises ``MemoryNotFoundError`` for an unknown id.
    """
    async with _exclusive(pending_id):
        record = await _get_unresolved(manager, pending_id)
        await manager.reject(pending_id)
        if record is None:
            return False
        await _audit(record, approved=False, source=source, batch=batch)
        return True


async def batch_approve_pending(
    manager: MemoryManager, pending_ids: list[str], *, source: PendingReviewSource
) -> tuple[int, list[str]]:
    """Approve many proposals one by one; returns ``(success_count, failed_ids)``.

    A proposal that was already resolved counts as a success: the user's intent already holds.
    A proposal whose target changed since it was queued is reported as failed and stays pending.
    """
    success = 0
    failed: list[str] = []
    for pending_id in dict.fromkeys(pending_ids):
        try:
            await approve_pending(manager, pending_id, source=source, batch=True)
            success += 1
        except PendingTargetChangedError:
            logger.info("Pending memory %s is stale (its target changed); left pending", pending_id)
            failed.append(pending_id)
        except Exception:
            logger.warning("Batch approve failed for pending memory %s", pending_id, exc_info=True)
            failed.append(pending_id)
    return success, failed


async def batch_reject_pending(manager: MemoryManager, pending_ids: list[str], *, source: PendingReviewSource) -> int:
    """Reject many proposals one by one; returns how many were really rejected (unknown or resolved ids are skipped)."""
    rejected = 0
    for pending_id in dict.fromkeys(pending_ids):
        try:
            rejected += await reject_pending(manager, pending_id, source=source, batch=True)
        except MemoryNotFoundError:
            continue
    return rejected


async def _get_unresolved(manager: MemoryManager, pending_id: str) -> PendingRecord | None:
    """Return the record only while it still awaits review, so a stale repeat is never audited twice."""
    record = await manager.get_pending(pending_id)
    return record if record is not None and record.status == "pending" else None


async def _audit(
    record: PendingRecord,
    *,
    approved: bool,
    source: PendingReviewSource,
    batch: bool,
    edited: bool = False,
) -> None:
    verdict = "approved" if approved else "rejected"
    scope = " in batch" if batch else ""
    summary = f"Pending memory {verdict}{scope}."
    if approved:
        summary += _APPROVED_SUFFIX.get(record.resolution_action, "")

    await _best_effort(
        record.id,
        record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_APPROVED if approved else ExperienceEventType.REVIEW_REJECTED,
                entity_type=ExperienceEntityType.REVIEW,
                entity_id=record.id,
                lineage_id=f"memory:{record.id}",
                outcome=verdict,
                summary=f"Review {verdict} for memory:{record.id}",
                artifact_refs={"review_type": "memory", "memory_type": record.memory_type.value},
                detail={
                    "review_type": "memory",
                    "review_id": record.id,
                    "batch": batch,
                    "edited": edited,
                    "resolution_action": record.resolution_action.value,
                    "target_memory_id": record.target_memory_id,
                },
            )
        ),
    )
    await _best_effort(
        record.id,
        record_pending_event(
            kind=MemoryOperationKind.APPROVE if approved else MemoryOperationKind.REJECT,
            memory_id=record.id,
            memory_type=record.memory_type.value,
            summary=summary,
            source=source,
        ),
    )


async def record_pending_event(
    *,
    kind: MemoryOperationKind,
    memory_id: str,
    memory_type: str | None,
    summary: str,
    source: PendingReviewSource = PendingReviewSource.WEB_API,
) -> None:
    """Append one review outcome to the memory operation ledger (also used by conflict arbitration)."""
    async with get_session() as db:
        await MemoryOperationLedgerService(db).record_event(
            kind=kind,
            status=MemoryOperationStatus.SUCCESS,
            summary=summary,
            memory_id=memory_id,
            memory_type=memory_type,
            source=source.value,
            target_kind="pending_memory",
            target_id=memory_id,
            commit=True,
        )


async def _best_effort(pending_id: str, write: Awaitable[object]) -> None:
    try:
        await write
    except Exception:
        logger.warning("Failed to record the audit trail for pending memory %s", pending_id, exc_info=True)
