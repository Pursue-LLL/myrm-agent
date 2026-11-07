"""SQLiteRelationalStore unit tests — query-error and corruption fail-fast branches."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.relational.exceptions import (
    CorruptedMemoryIndexError,
    RelationalQueryError,
)
from tests.support.relational_records import make_pending, make_rule


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteRelationalStore:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s  # type: ignore[misc]
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
