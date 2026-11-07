"""SQLiteRelationalStore unit tests — pending approval queue."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import (
    MemoryType,
    PendingRecord,
    PendingResolutionAction,
)
from tests.support.relational_records import make_pending


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s
    await s.close()


# ── Pending ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_and_get_pending(store: SQLiteRelationalStore) -> None:
    record = make_pending()
    pid = await store.submit_pending(record)
    fetched = await store.get_pending(pid)
    assert fetched is not None
    assert fetched.content == "test memory"
    assert fetched.status == "pending"


@pytest.mark.asyncio
async def test_pending_action_metadata_round_trips(store: SQLiteRelationalStore) -> None:
    """resolution_action / target_memory_id / target_content survive persistence.

    The approval dispatcher and review UI read these fields, so a column/order
    regression in the pending table must fail loudly here.
    """
    record = PendingRecord(
        memory_type=MemoryType.SEMANTIC,
        content="User now works at Google",
        resolution_action=PendingResolutionAction.CORRECT,
        target_memory_id="mem-old",
        target_content="User works at ByteDance",
    )

    pid = await store.submit_pending(record)
    fetched = await store.get_pending(pid)

    assert fetched is not None
    assert fetched.resolution_action == PendingResolutionAction.CORRECT
    assert fetched.target_memory_id == "mem-old"
    assert fetched.target_content == "User works at ByteDance"


@pytest.mark.asyncio
async def test_pending_exists(store: SQLiteRelationalStore) -> None:
    await store.submit_pending(make_pending("unique content"))
    assert await store.pending_exists("semantic", "unique content") is True
    assert await store.pending_exists("semantic", "other") is False


@pytest.mark.asyncio
async def test_mark_pending(store: SQLiteRelationalStore) -> None:
    record = make_pending()
    pid = await store.submit_pending(record)
    await store.mark_pending(pid, "approved")
    fetched = await store.get_pending(pid)
    assert fetched is not None
    assert fetched.status == "approved"
    assert fetched.resolved_at is not None


@pytest.mark.asyncio
async def test_list_and_count_pending(store: SQLiteRelationalStore) -> None:
    for i in range(3):
        await store.submit_pending(make_pending(f"mem_{i}"))
    pending = await store.list_pending()
    assert len(pending) == 3
    assert await store.count_pending() == 3


@pytest.mark.asyncio
async def test_batch_mark_pending(store: SQLiteRelationalStore) -> None:
    ids = []
    for i in range(3):
        pid = await store.submit_pending(make_pending(f"batch_{i}"))
        ids.append(pid)
    count = await store.batch_mark_pending(ids[:2], "rejected")
    assert count == 2
    assert await store.count_pending() == 1


# ── Pending by source chat ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_pending_by_source_chat_id(store: SQLiteRelationalStore) -> None:
    """delete_pending_by_source_chat_id removes only matching records."""
    record = make_pending("chat-scoped")
    record.source_chat_id = "chat-1"
    await store.submit_pending(record)
    await store.submit_pending(make_pending("other"))

    deleted = await store.delete_pending_by_source_chat_id("chat-1")
    assert deleted == 1
    assert await store.count_pending() == 1


@pytest.mark.asyncio
async def test_count_pending_by_source_chat_id(store: SQLiteRelationalStore) -> None:
    """count_pending_by_source_chat_id counts only matching records."""
    for i in range(3):
        record = make_pending(f"chat-{i}")
        record.source_chat_id = "chat-1"
        await store.submit_pending(record)
    await store.submit_pending(make_pending("other"))

    assert await store.count_pending_by_source_chat_id("chat-1") == 3
    assert await store.count_pending_by_source_chat_id("missing") == 0


@pytest.mark.asyncio
async def test_batch_mark_pending_empty_list(store: SQLiteRelationalStore) -> None:
    """batch_mark_pending with empty list returns 0 without touching DB."""
    assert await store.batch_mark_pending([], "rejected") == 0
