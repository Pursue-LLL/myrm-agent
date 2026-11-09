"""SQLiteRelationalStore unit tests — query-error and corruption fail-fast branches."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.relational.exceptions import (
    CorruptedMemoryIndexError,
    RelationalQueryError,
    RelationalStoreError,
)
from tests.support.relational_records import make_pending, make_rule

STORE_MODULE = "myrm_agent_harness.toolkits.memory.relational.sqlite_store"


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s
    await s.close()


# ── Error branches ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_error_branches_raise(store: SQLiteRelationalStore, monkeypatch) -> None:
    """DB failures surface as RelationalQueryError across CRUD methods."""

    class _ExplodingCursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("db exploded")

        async def commit(self):
            raise RuntimeError("db exploded")

        async def fetchone(self):
            raise RuntimeError("db exploded")

        async def fetchall(self):
            raise RuntimeError("db exploded")

    class _ExplodingConnection:
        def execute(self, *_args, **_kwargs):
            return _ExplodingCursor()

        async def commit(self):
            raise RuntimeError("db exploded")

    async def _fake_connection():
        return _ExplodingConnection()

    monkeypatch.setattr(store, "_get_connection", _fake_connection)

    for call in (
        lambda: store.get_profile("k"),
        lambda: store.get_profile_snapshot("k"),
        lambda: store.set_profile("k", "v"),
        lambda: store.delete_profile("k"),
        lambda: store.list_profiles(),
        lambda: store.count_profiles(),
        lambda: store.create_rule(make_rule()),
        lambda: store.get_rule("r"),
        lambda: store.search_rules("q"),
        lambda: store.list_rules(),
        lambda: store.count_rules(),
        lambda: store.update_rule("r", make_rule()),
        lambda: store.delete_rule("r"),
        lambda: store.delete_all(),
        lambda: store.submit_pending(make_pending()),
        lambda: store.get_pending("p"),
        lambda: store.pending_exists("semantic", "c"),
        lambda: store.mark_pending("p", "approved"),
        lambda: store.list_pending(),
        lambda: store.count_pending(),
        lambda: store.batch_mark_pending(["p"], "approved"),
        lambda: store.delete_pending_by_source_chat_id("chat"),
        lambda: store.count_pending_by_source_chat_id("chat"),
    ):
        with pytest.raises(RelationalQueryError):
            await call()


@pytest.mark.asyncio
async def test_corrupted_memory_index_fail_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "corrupted_test.db"
    store = SQLiteRelationalStore(str(db_file))
    await store.set_profile("init_key", "init_val")

    # Mock quick_check returning corruption
    class _CorruptCursor:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def fetchall(self):
            return [("tree cell 17 out of order",)]

    conn = await store._get_connection()
    orig_execute = conn.execute

    def _corrupt_execute(sql, *args, **kwargs):
        if "PRAGMA quick_check" in str(sql):
            return _CorruptCursor()
        return orig_execute(sql, *args, **kwargs)

    monkeypatch.setattr(conn, "execute", _corrupt_execute)

    # A failure is only corruption when a fresh connection reproduces it (a stale
    # long-lived connection alone is not), so the fresh check reports it too.
    class _FreshCorruptConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        def execute(self, *_args, **_kwargs):
            return _CorruptCursor()

    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.memory.relational.sqlite_store.aiosqlite.connect",
        lambda *_args, **_kwargs: _FreshCorruptConnection(),
    )

    # 1. Direct integrity check returns False
    ok, detail = await store.check_integrity()
    assert ok is False
    assert "tree cell 17 out of order" in detail

    # 2. assert_store_integrity and writes must Fail-Fast with CorruptedMemoryIndexError
    with pytest.raises(CorruptedMemoryIndexError) as exc_info:
        await store.assert_store_integrity()
    assert "failed quick_check" in str(exc_info.value)
    assert exc_info.value.index_type == "sqlite_relational"

    with pytest.raises(CorruptedMemoryIndexError) as exc_write:
        await store.set_profile("should_fail", "corrupt_data")
    assert "failed quick_check" in str(exc_write.value)

    await store.close()


# ── Exact-fact index operations and connection setup ────────────────


def failing(operation: str, message: str) -> AbstractContextManager[object]:
    """Make one of the store module's operations raise ``message``."""
    return patch(f"{STORE_MODULE}.{operation}", side_effect=RuntimeError(message))


async def record(store: SQLiteRelationalStore, identifier: str) -> None:
    await store.record_exact_fact(
        memory_id="m1",
        user_id="user",
        content=f"host at {identifier}",
        identifiers=[identifier],
        primary_namespace="ns",
    )


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("save_exact_fact", lambda store: record(store, "10.0.0.1:80")),
        ("delete_exact_fact", lambda store: store.delete_exact_fact("m1")),
        ("search_exact_facts", lambda store: store.search_fts5("10.0.0.1:80")),
    ],
    ids=["record", "delete", "search"],
)
async def test_a_failing_index_operation_surfaces_and_leaves_the_store_usable(
    store: SQLiteRelationalStore, operation: str, call: Callable[[SQLiteRelationalStore], Awaitable[object]]
) -> None:
    with failing(operation, "index exploded"), pytest.raises(RelationalQueryError, match="index exploded"):
        await call(store)

    # The index write lock is not left held: the next write completes instead of waiting for it.
    await asyncio.wait_for(record(store, "10.0.0.2:81"), timeout=5)
    assert [hit.memory.id for hit in await store.search_fts5("10.0.0.2:81")] == ["m1"]


async def test_a_failure_that_reads_as_corruption_drops_the_connection_and_the_next_write_reconnects(
    store: SQLiteRelationalStore,
) -> None:
    dropped = await store._get_connection()

    with failing("save_exact_fact", "database disk image is malformed"), pytest.raises(CorruptedMemoryIndexError):
        await record(store, "10.0.0.1:80")
    await dropped.close()

    await asyncio.wait_for(record(store, "10.0.0.2:81"), timeout=5)
    assert [hit.memory.id for hit in await store.search_fts5("10.0.0.2:81")] == ["m1"]


async def test_a_failed_schema_setup_is_retried_by_the_next_call(store: SQLiteRelationalStore) -> None:
    with failing("init_relational_schema", "disk is full"), pytest.raises(RelationalStoreError, match="disk is full"):
        await store.set_profile("language", "zh")

    await store.set_profile("language", "zh")

    assert await store.get_profile("language") == "zh"


@pytest.mark.parametrize(
    ("message", "expected"),
    [("database disk image is malformed", CorruptedMemoryIndexError), ("lock timeout", RelationalQueryError)],
    ids=["reads-as-corruption", "other-failure"],
)
async def test_an_integrity_query_failure_is_corruption_only_when_it_reads_as_corruption(
    store: SQLiteRelationalStore, message: str, expected: type[RelationalStoreError]
) -> None:
    with patch.object(store, "_quick_check_rows", side_effect=RuntimeError(message)), pytest.raises(expected):
        await store.assert_store_integrity()


async def test_the_integrity_check_of_a_closed_store_says_so(store: SQLiteRelationalStore) -> None:
    await store.close()

    assert await store.check_integrity() == (False, "Store has been closed")
