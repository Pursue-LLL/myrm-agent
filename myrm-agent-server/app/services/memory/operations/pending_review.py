"""Pending memory review: approve or reject queued proposals and record the audit trail.

[INPUT]
- myrm_agent_harness.toolkits.memory::{MemoryManager, MemoryOperationKind, MemoryOperationStatus} (POS: 记忆管理器与操作账本枚举)
- myrm_agent_harness.toolkits.memory.types::{PendingRecord, PendingResolutionAction} (POS: 审批队列记录)
- app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)
- app.services.skills.experience_ledger::{record_experience_event} (POS: 学习资产事件账本)

[OUTPUT]
- PendingReviewSource: 审批入口来源（写入操作账本 source 字段）
- approve_pending / reject_pending / batch_approve_pending / batch_reject_pending: 审批动作 + 审计
- record_pending_event: 向操作账本追加审批类事件（冲突仲裁复用）

[POS]
审批队列（harness `pending_records`）的唯一业务审批入口。Web、指挥中心与 IM 三处都经此函数批准/拒绝，
保证每一次生效的审批（含「批准后把旧记忆移入回收站」）都有经验账本与操作账本记录。
审计为尽力而为：账本写入失败只记录 WARNING，不会让已生效的审批返回错误。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from enum import StrEnum

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus
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


async def approve_pending(
    manager: MemoryManager,
    pending_id: str,
    *,
    source: PendingReviewSource,
    edited_content: str | None = None,
) -> None:
    """Approve one queued proposal; raises the harness error (e.g. ``MemoryNotFoundError``) on failure."""
    record = await _get_unresolved(manager, pending_id)
    await manager.approve(pending_id, edited_content=edited_content)
    if record is not None:
        await _audit(record, approved=True, source=source, batch=False, edited=edited_content is not None)


async def reject_pending(manager: MemoryManager, pending_id: str, *, source: PendingReviewSource) -> None:
    """Reject one queued proposal; raises ``MemoryNotFoundError`` for an unknown id."""
    record = await _get_unresolved(manager, pending_id)
    await manager.reject(pending_id)
    if record is not None:
        await _audit(record, approved=False, source=source, batch=False)


async def batch_approve_pending(
    manager: MemoryManager, pending_ids: list[str], *, source: PendingReviewSource
) -> tuple[int, list[str]]:
    """Approve many proposals; returns ``(success_count, failed_ids)`` and audits only the applied ones."""
    records = await _load_unresolved(manager, pending_ids)
    success, failed = await manager.batch_approve(pending_ids)
    failed_ids = set(failed)
    for pending_id, record in records.items():
        if pending_id not in failed_ids:
            await _audit(record, approved=True, source=source, batch=True)
    return success, failed


async def batch_reject_pending(manager: MemoryManager, pending_ids: list[str], *, source: PendingReviewSource) -> int:
    """Reject many proposals; returns the number rejected and audits only records that really flipped."""
    records = await _load_unresolved(manager, pending_ids)
    rejected = await manager.batch_reject(pending_ids)
    for pending_id, record in records.items():
        current = await manager.get_pending(pending_id)
        if current is not None and current.status == "rejected":
            await _audit(record, approved=False, source=source, batch=True)
    return rejected


async def _get_unresolved(manager: MemoryManager, pending_id: str) -> PendingRecord | None:
    """Return the record only while it still awaits review, so a stale repeat is never audited twice."""
    record = await manager.get_pending(pending_id)
    return record if record is not None and record.status == "pending" else None


async def _load_unresolved(manager: MemoryManager, pending_ids: list[str]) -> dict[str, PendingRecord]:
    records: dict[str, PendingRecord] = {}
    for pending_id in dict.fromkeys(pending_ids):
        record = await _get_unresolved(manager, pending_id)
        if record is not None:
            records[pending_id] = record
    return records


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
