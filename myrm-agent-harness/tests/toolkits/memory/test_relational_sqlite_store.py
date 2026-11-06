"""SQLiteRelationalStore unit tests — profile, snapshot, lifecycle, exact-fact search bounds."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.protocols.relational import RelationalStoreProtocol
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from myrm_agent_harness.toolkits.memory.types import MemoryScope
from tests.support.relational_records import make_pending, make_rule


@pytest.fixture
async def store(tmp_path: Path) -> SQLiteRelationalStore:
    s = SQLiteRelationalStore(str(tmp_path / "test_rel.db"))
    yield s  # type: ignore[misc]
    await s.close()


# ── Protocol satisfaction ────────────────────────────────────────────


def test_satisfies_protocol(tmp_path: Path) -> None:
    s = SQLiteRelationalStore(str(tmp_path / "proto.db"))
    assert isinstance(s, RelationalStoreProtocol)


# ── Profile ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_and_get_profile(store: SQLiteRelationalStore) -> None:
    await store.set_profile("language", "zh")
    val = await store.get_profile("language")
    assert val == "zh"


@pytest.mark.asyncio
async def test_get_profile_not_found(store: SQLiteRelationalStore) -> None:
    val = await store.get_profile("nonexistent")
    assert val is None


@pytest.mark.asyncio
async def test_set_profile_upsert(store: SQLiteRelationalStore) -> None:
    await store.set_profile("lang", "en")
    await store.set_profile("lang", "zh")
    val = await store.get_profile("lang")
    assert val == "zh"


@pytest.mark.asyncio
async def test_delete_profile(store: SQLiteRelationalStore) -> None:
    await store.set_profile("k", "v")
    deleted = await store.delete_profile("k")
    assert deleted is True
    assert await store.get_profile("k") is None


@pytest.mark.asyncio
async def test_list_and_count_profiles(store: SQLiteRelationalStore) -> None:
    for i in range(5):
        await store.set_profile(f"key_{i}", f"val_{i}")
    profiles = await store.list_profiles()
    assert len(profiles) == 5
    count = await store.count_profiles()
    assert count == 5


@pytest.mark.asyncio
async def test_list_profiles_pagination(store: SQLiteRelationalStore) -> None:
    for i in range(10):
        await store.set_profile(f"k{i}", f"v{i}")
        page = await store.list_profiles(limit=3, offset=0)
    assert len(page) == 3


@pytest.mark.asyncio
async def test_profiles_are_isolated_by_namespace(store: SQLiteRelationalStore) -> None:
    await store.set_profile(
        "language",
        "zh",
        scope=MemoryScope(
            primary_namespace="channel:telegram",
            namespaces=["channel:telegram"],
            channel_id="telegram",
        ),
    )
    await store.set_profile(
        "language",
        "en",
        scope=MemoryScope(
            primary_namespace="channel:feishu",
            namespaces=["channel:feishu"],
            channel_id="feishu",
        ),
    )

    assert await store.get_profile("language", namespaces=["channel:telegram"]) == "zh"
    assert await store.get_profile("language", namespaces=["channel:feishu"]) == "en"
    profiles = await store.list_profiles(namespaces=["channel:telegram"])
    assert len(profiles) == 1
    assert profiles[0].scope.channel_id == "telegram"


# ── Delete all ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_all(store: SQLiteRelationalStore) -> None:
    await store.set_profile("k", "v")
    await store.create_rule(make_rule())
    await store.submit_pending(make_pending())
    count = await store.delete_all()
    assert count >= 3
    assert await store.count_profiles() == 0
    assert await store.count_rules() == 0
    assert await store.count_pending() == 0


# ── Lifecycle ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_context_manager(tmp_path: Path) -> None:
    async with SQLiteRelationalStore(str(tmp_path / "ctx.db")) as s:
        await s.set_profile("test", "value")
        assert await s.get_profile("test") == "value"


# ── Profile snapshot ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_profile_snapshot_exists(store: SQLiteRelationalStore) -> None:
    await store.set_profile("language", "zh")
    snap = await store.get_profile_snapshot("language")
    assert snap.exists is True
    assert snap.key == "language"
    assert snap.value == "zh"
    assert snap.revision is not None
    assert snap.updated_at is not None


@pytest.mark.asyncio
async def test_get_profile_snapshot_not_found(store: SQLiteRelationalStore) -> None:
    snap = await store.get_profile_snapshot("nonexistent")
    assert snap.exists is False
    assert snap.key == "nonexistent"
    assert "missing" in snap.revision


# ── Lifecycle edge cases ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_operations_after_close_raise(store: SQLiteRelationalStore) -> None:
    """Any operation after close() must raise RelationalConnectionError."""
    from myrm_agent_harness.toolkits.memory.relational.exceptions import (
        RelationalConnectionError,
    )

    await store.close()
    with pytest.raises(RelationalConnectionError):
        await store.get_profile("language")


@pytest.mark.asyncio
async def test_close_is_idempotent(store: SQLiteRelationalStore) -> None:
    """close() can be called multiple times safely."""
    await store.set_profile("k", "v")
    await store.close()
    await store.close()
    assert store._closed is True


# ── Exact fact search time bounds ────────────────────────────────────

_OLD_UUID = "11111111-2222-3333-a444-555555555555"
_NEW_UUID = "66666666-7777-1888-b999-000000000000"
_STALE_CREATED_AT = "2020-01-01T00:00:00+00:00"


async def _record_two_exact_facts(store: SQLiteRelationalStore) -> None:
    """Write two exact facts, backdate the first to a stale created_at."""
    await store.record_exact_fact(
        memory_id="m-old",
        user_id="u1",
        content="old deploy runbook fact",
        identifiers=[_OLD_UUID],
    )
    await store.record_exact_fact(
        memory_id="m-new",
        user_id="u1",
        content="new deploy runbook fact",
        identifiers=[_NEW_UUID],
    )
    conn = await store._get_connection()
    await conn.execute(
        "UPDATE exact_fact_identifiers SET created_at = ? WHERE memory_id = ?",
        (_STALE_CREATED_AT, "m-old"),
    )
    await conn.commit()


@pytest.mark.asyncio
async def test_search_fts5_time_bounds_filter_btree_identifier_matches(
    store: SQLiteRelationalStore,
) -> None:
    """since/until must filter the deterministic identifier path, not just BM25."""
    await _record_two_exact_facts(store)
    q = f"{_OLD_UUID} {_NEW_UUID}"

    ids_all = sorted(m.memory.id for m in await store.search_fts5(q, 10))
    assert ids_all == ["m-new", "m-old"]

    ids_since = sorted(m.memory.id for m in await store.search_fts5(q, 10, since=datetime(2024, 1, 1, tzinfo=UTC)))
    assert ids_since == ["m-new"]

    ids_until = sorted(m.memory.id for m in await store.search_fts5(q, 10, until=datetime(2024, 1, 1, tzinfo=UTC)))
    assert ids_until == ["m-old"]


@pytest.mark.asyncio
async def test_search_fts5_time_bounds_filter_fts5_keyword_matches(
    store: SQLiteRelationalStore,
) -> None:
    """since/until must also constrain the FTS5 virtual-table path via the identifiers table."""
    await _record_two_exact_facts(store)

    ids_all = sorted(m.memory.id for m in await store.search_fts5("runbook", 10))
    assert ids_all == ["m-new", "m-old"]

    ids_until = sorted(
        m.memory.id for m in await store.search_fts5("runbook", 10, until=datetime(2024, 1, 1, tzinfo=UTC))
    )
    assert ids_until == ["m-old"]

    ids_since = sorted(
        m.memory.id for m in await store.search_fts5("runbook", 10, since=datetime(2024, 1, 1, tzinfo=UTC))
    )
    assert ids_since == ["m-new"]


@pytest.mark.asyncio
async def test_search_fts5_time_bounds_naive_datetimes_are_coerced(
    store: SQLiteRelationalStore,
) -> None:
    """Naive bounds are treated as UTC so they still compare against the +00:00 storage format."""
    await _record_two_exact_facts(store)
    q = f"{_OLD_UUID} {_NEW_UUID}"

    ids_until = sorted(m.memory.id for m in await store.search_fts5(q, 10, until=datetime(2024, 1, 1)))
    assert ids_until == ["m-old"]

    ids_since = sorted(m.memory.id for m in await store.search_fts5(q, 10, since=datetime(2024, 1, 1)))
    assert ids_since == ["m-new"]
