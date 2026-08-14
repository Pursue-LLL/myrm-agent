"""Persistent retry queue for memory extraction.

[INPUT]
app.database.models.memory::MemoryExtractRetryModel (POS: 记忆提取重试队列 ORM 模型)
app.database.connection::get_session (POS: 数据库会话)

[OUTPUT]
enqueue / claim_due / delete / mark_failure / clear_for_chat: SQLite-backed queue operations.

[POS]
Business-layer durable queue. Backs both the GUI manual retry and auto-recovery of
session-end auto-extract failures, so in-flight work survives service restarts.
Single-process semantics: a worker keeps an in-process running set, so rows are
never double-processed; on crash the row stays pending and the startup sweep reclaims it.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.database.models.memory import MemoryExtractRetryModel

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 60
BACKOFF_MAX_SECONDS = 30 * 60

EnqueueResult = Literal["queued", "already_queued"]


def _backoff_delay(attempt: int) -> timedelta:
    delay = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    return timedelta(seconds=min(delay, BACKOFF_MAX_SECONDS))


async def enqueue(chat_id: str, *, reset_failed: bool) -> EnqueueResult:
    """Idempotently enqueue a chat for extraction retry.

    - No row -> insert as pending, due immediately.
    - Pending row -> already_queued (keeps the existing schedule).
    - Failed row -> reset to pending only when ``reset_failed`` (manual retry).
    """
    from app.database.connection import get_session

    async with get_session() as db:
        row = await db.get(MemoryExtractRetryModel, chat_id)
        if row is None:
            db.add(
                MemoryExtractRetryModel(
                    chat_id=chat_id,
                    status="pending",
                    attempt=0,
                    next_attempt_at=datetime.now(UTC),
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                # Concurrent enqueue won the race and inserted the row first.
                return "already_queued"
            return "queued"
        if row.status == "pending" or not reset_failed:
            return "already_queued"
        row.status = "pending"
        row.attempt = 0
        row.next_attempt_at = datetime.now(UTC)
        row.last_error = None
        await db.commit()
        return "queued"


async def claim_due(now: datetime, *, excluding: frozenset[str]) -> list[tuple[str, int]]:
    """Claim due pending chats, returning (chat_id, attempt) pairs.

    Increments ``attempt`` atomically so the caller knows which attempt slot was
    consumed. Rows currently running in-process (``excluding``) are skipped.
    """
    from app.database.connection import get_session

    async with get_session() as db:
        result = await db.execute(
            select(MemoryExtractRetryModel.chat_id, MemoryExtractRetryModel.attempt)
            .where(
                MemoryExtractRetryModel.status == "pending",
                MemoryExtractRetryModel.next_attempt_at <= now,
                MemoryExtractRetryModel.chat_id.not_in(excluding),
            )
            .order_by(MemoryExtractRetryModel.next_attempt_at)
        )
        rows = [(chat_id, attempt) for chat_id, attempt in result.all()]
        if not rows:
            return []
        chat_ids = [chat_id for chat_id, _ in rows]
        await db.execute(
            update(MemoryExtractRetryModel)
            .where(MemoryExtractRetryModel.chat_id.in_(chat_ids))
            .values(attempt=MemoryExtractRetryModel.attempt + 1)
        )
        await db.commit()
        return [(chat_id, attempt + 1) for chat_id, attempt in rows]


async def delete(chat_id: str) -> None:
    """Remove the queue row after a successful extraction."""
    from app.database.connection import get_session

    async with get_session() as db:
        await db.execute(
            sa_delete(MemoryExtractRetryModel).where(
                MemoryExtractRetryModel.chat_id == chat_id
            )
        )
        await db.commit()


async def mark_failure(chat_id: str, attempt: int, error: str) -> bool:
    """Record a failed attempt with exponential backoff.

    Returns True when retries are exhausted (row marked failed), False otherwise.
    """
    from app.database.connection import get_session

    async with get_session() as db:
        row = await db.get(MemoryExtractRetryModel, chat_id)
        if row is None:
            return True
        row.last_error = error[:500]
        if attempt >= MAX_ATTEMPTS:
            row.status = "failed"
            await db.commit()
            return True
        row.status = "pending"
        row.next_attempt_at = datetime.now(UTC) + _backoff_delay(attempt)
        await db.commit()
        return False


async def clear_for_chat(chat_id: str) -> None:
    """Drop pending retry work when a chat is deleted (soft or permanent)."""
    from app.database.connection import get_session

    async with get_session() as db:
        await db.execute(
            sa_delete(MemoryExtractRetryModel).where(
                MemoryExtractRetryModel.chat_id == chat_id
            )
        )
        await db.commit()


__all__ = [
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_MAX_SECONDS",
    "MAX_ATTEMPTS",
    "claim_due",
    "clear_for_chat",
    "delete",
    "enqueue",
    "mark_failure",
]
