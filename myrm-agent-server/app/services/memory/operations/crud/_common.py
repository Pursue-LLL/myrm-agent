"""Shared helpers for memory CRUD handlers."""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

from app.database.connection import get_session
from app.services.memory.operation_ledger import MemoryOperationLedgerService

logger = logging.getLogger(__name__)


_SORT_KEYS: dict[str, str] = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "importance": "importance",
}


async def _record_memory_event(
    *,
    kind: MemoryOperationKind,
    summary: str,
    memory_id: str | None = None,
    memory_type: str | None = None,
    status: MemoryOperationStatus = MemoryOperationStatus.SUCCESS,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> None:
    async with get_session() as db:
        await MemoryOperationLedgerService(db).record_event(
            kind=kind,
            status=status,
            summary=summary,
            memory_id=memory_id,
            memory_type=memory_type,
            source="memory_crud_api",
            target_kind="memory" if memory_id else None,
            target_id=memory_id,
            metadata=metadata,
            commit=True,
        )


