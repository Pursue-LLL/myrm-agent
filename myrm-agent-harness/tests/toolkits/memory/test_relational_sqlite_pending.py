"""SQLiteRelationalStore unit tests — pending approval queue."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore, _pending_mixin, _schema
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalQueryError
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
async def test_an_identical_open_proposal_is_refused_with_an_empty_id(store: SQLiteRelationalStore) -> None:
    first = await store.submit_pending(make_pending("unique content"))
    second = await store.submit_pending(make_pending("unique content"))

    assert first != ""
    assert second == ""
    assert [record.id for record in await store.list_pending()] == [first]


@pytest.mark.asyncio
async def test_proposals_that_differ_in_content_or_type_are_all_queued(store: SQLiteRelationalStore) -> None:
    ids = [
        await store.submit_pending(make_pending("unique content")),
        await store.submit_pending(make_pending("other content")),
        await store.submit_pending(PendingRecord(memory_type=MemoryType.PROFILE, content="unique content")),
    ]

    assert "" not in ids
    assert await store.count_pending() == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["approved", "rejected"])
async def test_a_resolved_proposal_does_not_block_the_same_text_being_proposed_again(
    store: SQLiteRelationalStore, resolution: str
) -> None:
    first = await store.submit_pending(make_pending("unique content"))
    await store.mark_pending(first, resolution)

    again = await store.submit_pending(make_pending("unique content"))

    assert again not in ("", first)
    assert await store.count_pending() == 1


@pytest.mark.asyncio
async def test_a_reused_record_id_is_still_an_error(store: SQLiteRelationalStore) -> None:
    """Only an identical open proposal is turned away quietly; any other constraint failure surfaces."""
    record = make_pending("first text")
    await store.submit_pending(record)
    clash = make_pending("second text")
    clash.id = record.id

    with pytest.raises(RelationalQueryError):
        await store.submit_pending(clash)


@pytest.mark.asyncio
async def test_stores_sharing_one_database_queue_identical_proposals_once(tmp_path: Path) -> None:
    path = str(tmp_path / "shared.db")
    stores = [SQLiteRelationalStore(path), SQLiteRelationalStore(path)]
    try:
        for each in stores:
            await each.count_pending()

        ids = await asyncio.gather(
            *(each.submit_pending(make_pending("racing text")) for each in stores for _ in range(8))
        )

        assert len([pid for pid in ids if pid]) == 1
        assert await stores[0].count_pending() == 1
    finally:
        for each in stores:
            await each.close()


def _write_open_proposals(db_path: Path, rows: list[tuple[str, str, str]]) -> None:
    """A database of the current layout, as an older build left it: no unique index over the open proposals."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE pending_records (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, memory_type TEXT NOT NULL, content TEXT NOT NULL,
                memory_data TEXT, source_chat_id TEXT, source_message_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL, resolved_at TEXT, resolution_action TEXT NOT NULL DEFAULT 'store',
                target_memory_id TEXT, target_content TEXT, built_from_chats INTEGER NOT NULL DEFAULT 0)"""
        )
        conn.executemany(
            "INSERT INTO pending_records (id, user_id, memory_type, content, status, created_at) "
            "VALUES (?, 'default', 'semantic', ?, ?, '2020-01-01T00:00:00+00:00')",
            rows,
        )


@pytest.mark.asyncio
async def test_opening_a_database_whose_index_another_connection_builds_meanwhile_still_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "meanwhile_rel.db"
    _write_open_proposals(db_path, [("old-1", "same text", "pending")])

    def build_the_index_on_another_connection() -> str:
        # Evaluated after the bootstrap found no index and before it closes duplicates: the other connection wins.
        with sqlite3.connect(db_path) as other:
            other.execute(
                "CREATE UNIQUE INDEX idx_pending_open_proposal ON pending_records(memory_type, content) "
                "WHERE status = 'pending'"
            )
        return "2020-01-01T00:00:00+00:00"

    monkeypatch.setattr(_schema, "now_iso", build_the_index_on_another_connection)
    store = SQLiteRelationalStore(str(db_path))
    try:
        assert [record.id for record in await store.list_pending()] == ["old-1"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_a_database_holding_identical_open_proposals_keeps_the_oldest_open_and_closes_the_rest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "duplicates_rel.db"
    _write_open_proposals(
        db_path,
        [
            ("old-1", "same text", "pending"),
            ("old-2", "same text", "pending"),
            ("old-3", "same text", "pending"),
            ("old-4", "other text", "pending"),
            ("old-5", "same text", "rejected"),
        ],
    )

    for _ in range(2):
        store = SQLiteRelationalStore(str(db_path))
        try:
            assert sorted(record.id for record in await store.list_pending()) == ["old-1", "old-4"]
            assert await store.submit_pending(make_pending("same text")) == ""
        finally:
            await store.close()

    with sqlite3.connect(db_path) as conn:
        statuses = dict(conn.execute("SELECT id, status FROM pending_records"))
        resolved_at = dict(conn.execute("SELECT id, resolved_at FROM pending_records"))
    assert statuses == {
        "old-1": "pending",
        "old-2": "rejected",
        "old-3": "rejected",
        "old-4": "pending",
        "old-5": "rejected",
    }
    assert resolved_at["old-2"] is not None
    assert resolved_at["old-3"] is not None
    assert resolved_at["old-1"] is None
    assert resolved_at["old-5"] is None


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
