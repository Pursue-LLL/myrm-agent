"""Tests for the persistent memory extraction retry queue."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable

import pytest

from app.database.models import MemoryExtractRetryModel
from app.services.memory.extract_retry import extract_retry_queue as queue


@pytest.mark.asyncio
async def test_enqueue_inserts_new_pending_row(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    result = await queue.enqueue("chat-1", reset_failed=False)

    assert result == "queued"
    row = await fetch_retry_row("chat-1")
    assert row is not None
    assert row.status == "pending"
    assert row.attempt == 0


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_for_pending_row(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    result = await queue.enqueue("chat-1", reset_failed=False)

    assert result == "already_queued"
    row = await fetch_retry_row("chat-1")
    assert row is not None
    assert row.attempt == 0


@pytest.mark.asyncio
async def test_enqueue_does_not_reset_failed_row_unless_requested(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    await queue.mark_failure("chat-1", queue.MAX_ATTEMPTS, "boom")

    auto_result = await queue.enqueue("chat-1", reset_failed=False)
    assert auto_result == "already_queued"
    assert (await fetch_retry_row("chat-1")).status == "failed"

    manual_result = await queue.enqueue("chat-1", reset_failed=True)
    assert manual_result == "queued"
    row = await fetch_retry_row("chat-1")
    assert row.status == "pending"
    assert row.attempt == 0
    assert row.last_error is None


@pytest.mark.asyncio
async def test_claim_due_returns_only_due_rows_and_increments_attempt(
    test_db,
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    now = datetime.now(UTC)
    async with test_db() as db:
        db.add(
            MemoryExtractRetryModel(
                chat_id="chat-future",
                status="pending",
                attempt=0,
                next_attempt_at=now + timedelta(minutes=30),
            )
        )
        await db.commit()

    claimed = await queue.claim_due(now, excluding=frozenset())

    assert [chat_id for chat_id, _ in claimed] == ["chat-1"]
    assert claimed[0][1] == 1
    assert (await fetch_retry_row("chat-1")).attempt == 1


@pytest.mark.asyncio
async def test_claim_due_empty_queue_returns_empty_list() -> None:
    claimed = await queue.claim_due(datetime.now(UTC), excluding=frozenset())
    assert claimed == []


@pytest.mark.asyncio
async def test_claim_due_skips_running_rows(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    await queue.enqueue("chat-2", reset_failed=False)

    claimed = await queue.claim_due(datetime.now(UTC), excluding=frozenset({"chat-1"}))

    assert [chat_id for chat_id, _ in claimed] == ["chat-2"]


@pytest.mark.asyncio
async def test_mark_failure_schedules_exponential_backoff(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    before = datetime.now(UTC).replace(tzinfo=None)

    exhausted = await queue.mark_failure("chat-1", attempt=1, error="timeout")

    assert exhausted is False
    row = await fetch_retry_row("chat-1")
    assert row.status == "pending"
    assert row.next_attempt_at >= before + timedelta(seconds=queue.BACKOFF_BASE_SECONDS)
    assert row.last_error == "timeout"


@pytest.mark.asyncio
async def test_mark_failure_exhausts_after_max_attempts(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)

    exhausted = await queue.mark_failure("chat-1", attempt=queue.MAX_ATTEMPTS, error="permanent")

    assert exhausted is True
    row = await fetch_retry_row("chat-1")
    assert row.status == "failed"
    assert row.last_error == "permanent"


@pytest.mark.asyncio
async def test_mark_failure_for_missing_row_is_exhausted() -> None:
    exhausted = await queue.mark_failure("chat-ghost", attempt=1, error="boom")
    assert exhausted is True


@pytest.mark.asyncio
async def test_concurrent_enqueue_same_chat_is_race_safe(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    """Concurrent enqueues of a brand-new chat must never raise (primary-key race)."""
    results = await asyncio.gather(*(queue.enqueue("chat-race", reset_failed=False) for _ in range(8)))

    assert all(result in ("queued", "already_queued") for result in results)
    assert "queued" in results
    row = await fetch_retry_row("chat-race")
    assert row is not None
    assert row.attempt == 0


@pytest.mark.asyncio
async def test_delete_removes_row(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    await queue.delete("chat-1")
    assert await fetch_retry_row("chat-1") is None


@pytest.mark.asyncio
async def test_clear_for_chat_removes_row(
    fetch_retry_row: Callable[[str], Awaitable[MemoryExtractRetryModel | None]],
) -> None:
    await queue.enqueue("chat-1", reset_failed=False)
    await queue.clear_for_chat("chat-1")
    assert await fetch_retry_row("chat-1") is None
