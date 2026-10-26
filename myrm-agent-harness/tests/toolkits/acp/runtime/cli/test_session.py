"""``CliSessionBook``: bounded memory-first session records with best-effort write-through to a store."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.session import CliSessionBook
from myrm_agent_harness.toolkits.acp.types import CliSessionRecord

from ._fakes import RecordingStore

_RECORD = CliSessionRecord("cli-1", "/work")


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
async def test_a_remembered_record_is_read_back_without_touching_the_store() -> None:
    store = RecordingStore()
    book = CliSessionBook("test", store)
    book.remember("s1", _RECORD)

    assert await book.recorded("s1") == _RECORD
    assert store.ops == []


@pytest.mark.asyncio
async def test_a_memory_miss_loads_from_the_store_once() -> None:
    store = RecordingStore()
    store.records["s1"] = _RECORD
    book = CliSessionBook("test", store)

    assert await book.recorded("s1") == _RECORD
    assert await book.recorded("s1") == _RECORD
    assert store.ops == [("load", "s1")]


@pytest.mark.asyncio
async def test_without_a_store_an_unknown_session_has_no_record() -> None:
    assert await CliSessionBook("test").recorded("s1") is None


@pytest.mark.asyncio
async def test_a_record_just_loaded_is_not_written_back() -> None:
    store = RecordingStore()
    store.records["s1"] = _RECORD
    book = CliSessionBook("test", store)
    await book.recorded("s1")

    await book.persist("s1")

    assert store.ops == [("load", "s1")]


@pytest.mark.asyncio
async def test_persist_writes_a_new_record_once_and_a_replaced_record_again() -> None:
    store = RecordingStore()
    book = CliSessionBook("test", store)
    book.remember("s1", _RECORD)
    await book.persist("s1")
    await book.persist("s1")
    renewed = CliSessionRecord("cli-2", "/work")
    book.remember("s1", renewed)
    await book.persist("s1")

    assert [op for op, _ in store.ops] == ["save", "save"]
    assert store.records == {"s1": renewed}


@pytest.mark.asyncio
async def test_persist_without_a_record_or_a_store_is_a_no_op() -> None:
    store = RecordingStore()
    await CliSessionBook("test", store).persist("unknown")
    book = CliSessionBook("test")
    book.remember("s1", _RECORD)
    await book.persist("s1")

    assert store.ops == []


@pytest.mark.asyncio
async def test_a_failed_save_is_retried_by_the_next_persist() -> None:
    store = RecordingStore()
    store.failing = {"save"}
    book = CliSessionBook("test", store)
    book.remember("s1", _RECORD)

    await book.persist("s1")
    store.failing = set()
    await book.persist("s1")

    assert store.records == {"s1": _RECORD}
    assert [op for op, _ in store.ops] == ["save", "save"]


@pytest.mark.asyncio
async def test_a_failed_load_is_a_missing_record_not_an_error() -> None:
    store = RecordingStore()
    store.failing = {"load"}
    store.records["s1"] = _RECORD

    assert await CliSessionBook("test", store).recorded("s1") is None


@pytest.mark.asyncio
async def test_an_evicted_record_is_still_loadable_from_the_store() -> None:
    store = RecordingStore()
    store.records["s0"] = CliSessionRecord("cli-0", "/work")
    book = CliSessionBook("test", store)
    await book.recorded("s0")
    for index in range(1, 600):
        book.remember(f"s{index}", CliSessionRecord(f"cli-{index}", "/work"))
    assert "s0" not in book

    assert await book.recorded("s0") == CliSessionRecord("cli-0", "/work")


@pytest.mark.asyncio
async def test_clearing_memory_keeps_what_the_store_holds() -> None:
    store = RecordingStore()
    book = CliSessionBook("test", store)
    book.remember("s1", _RECORD)
    await book.persist("s1")

    book.clear_memory()

    assert len(book) == 0
    assert await book.recorded("s1") == _RECORD
