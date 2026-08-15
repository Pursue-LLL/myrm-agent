"""Guardian maintenance sub-tasks (conflict auto-resolve, archive purge).

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager / MemoryType
- myrm_agent_harness.toolkits.memory.types::MemoryStatus
- app.database.models::PendingMemory

[OUTPUT]
- auto_resolve_expired_conflicts: keep_old resolve for expired low-risk conflicts
- purge_expired_archives: hard-delete archived memories past their TTL

[POS]
Guardian 维护子任务（冲突自动解决、过期归档清理）。纯数据操作，不依赖调度状态，
由 memory_guardian 调度器在维护周期内调用。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from myrm_agent_harness.toolkits.memory.types import MemoryStatus

logger = logging.getLogger(__name__)


async def auto_resolve_expired_conflicts() -> int:
    """Resolve conflicts whose auto_resolve_at deadline has passed.

    Applies KEEP_OLD (safe default): the old memory stays, the conflicting
    new content is discarded. Returns the number of resolved conflicts.

    Conflicts whose ``conflict_auto_resolve_at`` is None (high-risk conflicts
    created with importance >= 0.9) never match the ``isnot(None)`` filter and
    are therefore never auto-resolved — they require explicit user action.
    """
    from sqlalchemy import func, update

    from app.database.connection import get_session
    from app.database.models import PendingMemory

    now = datetime.now(UTC)

    async with get_session() as db:
        stmt = (
            update(PendingMemory)
            .where(
                PendingMemory.is_conflict.is_(True),
                PendingMemory.status == "pending",
                PendingMemory.conflict_auto_resolve_at.isnot(None),
                PendingMemory.conflict_auto_resolve_at <= now,
            )
            .values(
                status="resolved",
                resolved_at=now,
                metadata_json=func.json_set(
                    PendingMemory.metadata_json,
                    "$.resolution",
                    "keep_old",
                    "$.auto_resolved",
                    True,
                ),
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


async def purge_expired_archives(manager: MemoryManager) -> int:
    """Hard-delete archived memories whose archive_expires_at TTL has passed.

    Returns total number of memories purged across all types.
    """
    total_purged = 0
    for mem_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        try:
            memories = await manager.list_memories(mem_type, limit=10000, include_archived=True)
            expired_ids: list[str] = []
            now = datetime.now(UTC)

            for m in memories:
                if getattr(m, "status", None) != MemoryStatus.ARCHIVED:
                    continue
                expires_str = getattr(m, "metadata", {}).get("archive_expires_at", "")
                if not expires_str:
                    continue
                try:
                    expires_at = datetime.fromisoformat(expires_str)
                    if now >= expires_at:
                        expired_ids.append(m.id)
                except (ValueError, TypeError):
                    continue

            if not expired_ids:
                continue

            coll = (
                manager.config.semantic_collection
                if mem_type == MemoryType.SEMANTIC
                else manager.config.episodic_collection
            )
            deleted = await manager.delete_memory(coll, expired_ids)
            total_purged += deleted
            logger.info(
                "Memory guardian: purged %d/%d expired archived %s memories",
                deleted,
                len(expired_ids),
                mem_type.value,
            )
        except Exception as exc:
            logger.warning("Memory guardian: failed to purge expired %s archives: %s", mem_type.value, exc)
    return total_purged
