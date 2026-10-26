"""``CliSessionBook``: bounded memory-first session records with best-effort write-through to a store."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.session import CliSessionBook
from myrm_agent_harness.toolkits.acp.types import CliSessionRecord

from ._fakes import RecordingStore


def test_memory_is_bounded_and_evicts_the_oldest_record_first() -> None:
    book = CliSessionBook("test")
    for index in range(600):
        book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))

    assert len(book) == 512
    assert "s0" not in book
    assert "s599" in book


def test_overwriting_a_record_at_capacity_evicts_nothing() -> None:
    book = CliSessionBook("test")
    for index in range(512):
        book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))
    book.remember("s5", CliSessionRecord("renewed", "/work"))

    assert len(book) == 512
    assert "s0" in book


@pytest.mark.asyncio
async def test_a_forgotten_record_is_written_again_when_the_same_record_comes_back() -> None:
    """Forgetting empties the store, so persisting an identical record afterwards must not be skipped."""
    store = RecordingStore()
    book = CliSessionBook("test", store)
    record = CliSessionRecord("cli-1", "/work")
    book.remember("s1", record)
    await book.persist("s1")
    await book.forget("s1")
    assert store.records == {}

    book.remember("s1", record)
    await book.persist("s1")

    assert store.records == {"s1": record}


@pytest.mark.asyncio
async def test_an_evicted_record_is_still_loadable_from_the_store() -> None:
    store = RecordingStore()
    store.records["s0"] = CliSessionRecord("cli-0", "/work")
    book = CliSessionBook("test", store)
    await book.resumable("s0", "/work")
    for index in range(1, 600):
        book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))
    assert "s0" not in book

    assert await book.resumable("s0", "/work") == CliSessionRecord("cli-0", "/work")


@pytest.mark.asyncio
async def test_a_record_the_store_failed_to_delete_is_not_read_back() -> None:
    store = RecordingStore()
    store.failing = {"delete"}
    record = CliSessionRecord("cli-1", "/work")
    store.records["s1"] = record
    book = CliSessionBook("test", store)
    book.remember("s1", record)

    await book.forget("s1")

    assert "s1" not in book
    assert await book.resumable("s1", "/work") is None
    assert store.ops == [("delete", "s1")]


@pytest.mark.asyncio
async def test_a_fresh_record_lifts_the_ban_on_reading_the_store_for_that_session() -> None:
    store = RecordingStore()
    store.failing = {"delete"}
    store.records["s1"] = CliSessionRecord("dead", "/work")
    book = CliSessionBook("test", store)
    await book.forget("s1")
    fresh = CliSessionRecord("fresh", "/work")
    book.remember("s1", fresh)
    await book.persist("s1")
    for index in range(600):
        book.remember(f"other-{index}", CliSessionRecord(f"cli-{index}", "/work"))
    assert "s1" not in book

    assert await book.resumable("s1", "/work") == fresh


@pytest.mark.asyncio
async def test_clearing_memory_returns_the_book_to_reading_the_store() -> None:
    store = RecordingStore()
    store.failing = {"delete"}
    store.records["s1"] = CliSessionRecord("dead", "/work")
    book = CliSessionBook("test", store)
    await book.forget("s1")

    book.clear_memory()

    assert await book.resumable("s1", "/work") == CliSessionRecord("dead", "/work")
