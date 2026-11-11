"""SQLiteRelationalStore unit tests — pending approval queue."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore, _pending_mixin
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


def built_from(content: str, written_from: str, *chats: str) -> PendingRecord:
    record = make_pending(content)
    record.source_chat_id = written_from
    record.memory_data = {"source_chat_ids": [written_from, *chats]}
    return record


@pytest.mark.asyncio
async def test_pending_by_source_chat_id_follows_every_chat_a_record_was_built_from(
    store: SQLiteRelationalStore,
) -> None:
    await store.submit_pending(built_from("built from b and a", "chat-b", "chat-a"))
    plain = make_pending("written in a")
    plain.source_chat_id = "chat-a"
    await store.submit_pending(plain)
    await store.submit_pending(built_from("built from c and d", "chat-c", "chat-d"))
    await store.submit_pending(make_pending("no chat"))

    assert await store.count_pending_by_source_chat_id("chat-a") == 2
    assert await store.delete_pending_by_source_chat_id("chat-a") == 2
    assert sorted(record.content for record in await store.list_pending()) == ["built from c and d", "no chat"]


@pytest.mark.asyncio
async def test_a_resolved_record_stays_linked_to_every_chat_it_was_built_from(store: SQLiteRelationalStore) -> None:
    pid = await store.submit_pending(built_from("built from b and a", "chat-b", "chat-a"))
    await store.mark_pending(pid, "approved")

    assert await store.count_pending_by_source_chat_id("chat-a") == 1
    assert await store.delete_pending_by_source_chat_id("chat-a") == 1
    assert await store.get_pending(pid) is None


@pytest.mark.asyncio
async def test_chat_ids_match_whole_and_literally(store: SQLiteRelationalStore) -> None:
    await store.submit_pending(built_from("a longer id", "chat-10", "chat-11"))
    await store.submit_pending(built_from("an id with an underscore", "chat_1", "chat_2"))
    await store.submit_pending(built_from("an id with a percent sign", "chat%1", "chat%2"))
    await store.submit_pending(built_from("an id with a quote", 'chat"1', 'chat"2'))

    # A prefix of a stored id is not that id, and LIKE wildcards in an id match only themselves.
    assert await store.count_pending_by_source_chat_id("chat-1") == 0
    assert await store.count_pending_by_source_chat_id("chat_") == 0
    assert await store.count_pending_by_source_chat_id("chatX2") == 0
    assert await store.count_pending_by_source_chat_id("chat%") == 0
    assert await store.count_pending_by_source_chat_id("chat_2") == 1
    assert await store.count_pending_by_source_chat_id("chat%2") == 1
    assert await store.count_pending_by_source_chat_id('chat"2') == 1
    assert await store.count_pending_by_source_chat_id("chat-11") == 1


@pytest.mark.asyncio
async def test_deleting_by_source_chat_id_removes_every_record_when_they_exceed_one_statement(
    store: SQLiteRelationalStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_pending_mixin, "_DELETE_CHUNK", 3)
    for index in range(8):
        await store.submit_pending(built_from(f"built {index}", f"chat-{index}", "chat-a"))
    await store.submit_pending(make_pending("no chat"))

    assert await store.delete_pending_by_source_chat_id("chat-a") == 8
    assert [record.content for record in await store.list_pending()] == ["no chat"]


@pytest.mark.asyncio
async def test_a_database_created_before_the_chat_lineage_column_gains_it_and_stays_readable(tmp_path: Path) -> None:
    db_path = tmp_path / "old_rel.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE pending_records (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, memory_type TEXT NOT NULL, content TEXT NOT NULL,
                memory_data TEXT, source_chat_id TEXT, source_message_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, resolved_at TEXT, resolution_action TEXT NOT NULL DEFAULT 'store',
                target_memory_id TEXT, target_content TEXT)"""
        )
        conn.execute(
            "INSERT INTO pending_records (id, user_id, memory_type, content, source_chat_id, created_at) "
            "VALUES ('old', 'default', 'semantic', 'proposed before', 'chat-a', '2020-01-01T00:00:00+00:00')"
        )
    store = SQLiteRelationalStore(str(db_path))
    try:
        await store.submit_pending(built_from("built after", "chat-b", "chat-a"))

        assert await store.count_pending_by_source_chat_id("chat-a") == 2
        assert [record.content for record in await store.list_pending()] == ["built after", "proposed before"]
    finally:
        await store.close()
    with sqlite3.connect(db_path) as conn:
        flags = dict(conn.execute("SELECT content, built_from_chats FROM pending_records"))
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(pending_records)")}
    assert flags == {"proposed before": 0, "built after": 1}
    assert "idx_pending_built_from_chats" in indexes


@pytest.mark.asyncio
async def test_batch_mark_pending_empty_list(store: SQLiteRelationalStore) -> None:
    """batch_mark_pending with empty list returns 0 without touching DB."""
    assert await store.batch_mark_pending([], "rejected") == 0
