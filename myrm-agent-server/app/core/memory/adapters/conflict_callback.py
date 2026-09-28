"""Conflict callback factory for memory consolidation.

[INPUT]
myrm_agent_harness.toolkits.memory.types::ConflictResolution (POS: 冲突决议枚举)
myrm_agent_harness.toolkits.memory.strategies.consolidation::ConflictCallback, ConflictContext (POS: 记忆整合冲突上下文)

[OUTPUT]
create_conflict_callback: 冲突持久化回调工厂

[POS]
记忆冲突适配层。处理记忆巩固引擎检测到的高重要性矛盾，
将其持久化为 PendingMemory 供用户在 UI 界面显式裁决。
"""

from __future__ import annotations

import logging
from datetime import UTC, timedelta
from datetime import datetime as dt
from typing import TYPE_CHECKING
from uuid import uuid4

from myrm_agent_harness.toolkits.memory.types import ConflictResolution
from sqlalchemy import select

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.strategies.consolidation import (
        ConflictCallback,
        ConflictContext,
    )

logger = logging.getLogger(__name__)

# Conflicts whose importance reaches this threshold are treated as high-risk:
# they are never auto-resolved (auto_resolve_at stays None) and always require
# explicit user resolution, so critical preferences (stack moves, relocations,
# allergy changes) cannot be silently reverted to the stale old memory.
_HIGH_RISK_IMPORTANCE = 0.9
_CONFLICT_AUTO_RESOLVE_HOURS = 72


async def _record_conflict_ledger_event(
    *,
    conflict_id: str,
    high_risk: bool,
    memory_type: str,
) -> None:
    """Record a conflict ledger event so the UI badge refreshes via SSE.

    Non-fatal: ledger failures must never affect conflict persistence.
    """
    try:
        from myrm_agent_harness.toolkits.memory import (
            MemoryOperationKind,
            MemoryOperationStatus,
        )

        from app.database.connection import get_session
        from app.services.memory.ledger.operation_ledger import (
            MemoryOperationLedgerService,
        )

        summary = (
            "New high-risk memory conflict awaiting your review."
            if high_risk
            else "New memory conflict awaiting your review."
        )
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.CONFLICT,
                status=MemoryOperationStatus.SUCCESS,
                summary=summary,
                memory_id=conflict_id,
                memory_type=memory_type,
                source="consolidation_conflict",
                target_kind="pending_memory",
                target_id=conflict_id,
                metadata={"high_risk": high_risk},
                commit=True,
            )
    except Exception:
        logger.warning(
            "Failed to record conflict ledger event for %s (non-fatal)",
            conflict_id,
            exc_info=True,
        )


def create_conflict_callback(agent_id: str | None = None) -> ConflictCallback:
    """Create an on_conflict callback that persists conflicts as PendingMemory rows.

    When the consolidation engine detects a high-importance contradiction it cannot
    auto-resolve, this callback writes a PendingMemory record with ``is_conflict=True``
    and returns ``ConflictResolution.PENDING`` so the framework keeps the old memory
    untouched until the user resolves it via the GUI.

    Low-risk conflicts (importance < ``_HIGH_RISK_IMPORTANCE``) get an
    ``conflict_auto_resolve_at`` deadline and are auto-resolved (keep_old) by the
    guardian if the user ignores them. High-risk conflicts keep ``conflict_auto_resolve_at``
    as None so they never silently auto-resolve — critical preferences always require
    explicit user action.
    """

    async def _on_conflict(ctx: ConflictContext) -> ConflictResolution:
        conflict_id = str(uuid4())
        high_risk = (ctx.importance or 0.0) >= _HIGH_RISK_IMPORTANCE
        auto_resolve_at = (
            None
            if high_risk
            else dt.now(UTC) + timedelta(hours=_CONFLICT_AUTO_RESOLVE_HOURS)
        )

        raw_type = getattr(ctx, "memory_type", None)
        if raw_type is not None and hasattr(raw_type, "value") and isinstance(raw_type.value, str):
            mem_type_str = raw_type.value
        elif isinstance(raw_type, str):
            mem_type_str = raw_type
        else:
            mem_type_str = "semantic"

        try:
            from app.database.connection import get_session
            from app.database.models import PendingMemory

            async with get_session() as db:
                existing_id = await db.scalar(
                    select(PendingMemory.id).where(
                        PendingMemory.is_conflict.is_(True),
                        PendingMemory.status == "pending",
                        PendingMemory.conflict_old_memory_id == ctx.old_memory_id,
                    )
                )
                if existing_id is not None:
                    # A pending conflict for the same old memory already exists
                    # (e.g. a later consolidation cycle re-detected it). Skip the
                    # duplicate so the pending queue never stacks identical rows.
                    logger.info(
                        "Conflict for old=%s already pending (%s), skipping duplicate",
                        ctx.old_memory_id,
                        existing_id,
                    )
                    return ConflictResolution.PENDING

                record = PendingMemory(
                    id=conflict_id,
                    agent_id=agent_id,
                    memory_type=mem_type_str,
                    content=ctx.new_content,
                    metadata_json={
                        "merge_suggestion": ctx.merge_suggestion,
                        "source": "consolidation_conflict",
                    },
                    confidence=ctx.accuracy_score,
                    status="pending",
                    is_conflict=True,
                    conflict_old_memory_id=ctx.old_memory_id,
                    conflict_old_content=ctx.old_content,
                    conflict_accuracy_score=ctx.accuracy_score,
                    conflict_importance=ctx.importance,
                    conflict_auto_resolve_at=auto_resolve_at,
                )
                db.add(record)
                await db.commit()

            logger.info(
                "Conflict persisted as PendingMemory %s (old=%s, importance=%.2f, high_risk=%s, auto_resolve=%s)",
                conflict_id,
                ctx.old_memory_id,
                ctx.importance or 0.0,
                high_risk,
                auto_resolve_at,
            )
            await _record_conflict_ledger_event(
                conflict_id=conflict_id,
                high_risk=high_risk,
                memory_type=mem_type_str,
            )
        except Exception:
            logger.warning(
                "Failed to persist conflict, falling back to KEEP_OLD",
                exc_info=True,
            )
            return ConflictResolution.KEEP_OLD

        return ConflictResolution.PENDING

    return _on_conflict
