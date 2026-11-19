"""A date alone as ``until`` names a whole UTC day: the search runs through the close of that day.

since/until match when a memory was saved, and both bounds are inclusive. A model that writes ``until=2026-03-31``
means "through March 31", but a bare date reads as 00:00, so a memory saved later that day was invisible and
``since=D until=D`` matched nothing. The sessions entry of memory_search_tool is pinned in test_time_filter.py.

[INPUT]
- toolkits.memory.agent_surface.memory_recall_formatting::parse_time_bound (POS: the since/until parser of the recall tools)
- toolkits.memory.agent_surface.memory_agent_tools::create_memory_tools (POS: facade of the agent memory tools)
- toolkits.memory.agent_surface.mcp_server::MemoryMCPServer (POS: MCP adapter exposing memory_recall)
- toolkits.memory.relational::SQLiteRelationalStore (POS: aiosqlite relational store that owns exact-fact search)
- tests.support.host_clock::pin_host_clock_to_utc_plus_8 (POS: holds the process clock at UTC+8 for the block it wraps)

[POS]
Contract guard for the end-of-day reading of a date-only until: at the parser, at the memory and MCP entries, and against a real store. Every test runs with the process clock at UTC+8, so a day read in the host's zone instead of UTC is hours off on a UTC host too.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting import parse_time_bound
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore
from tests.support.host_clock import pin_host_clock_to_utc_plus_8

_DAY_START = datetime(2026, 3, 31, tzinfo=UTC)
_DAY_END = datetime(2026, 3, 31, 23, 59, 59, 999999, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _host_clock_at_utc_plus_8() -> Iterator[None]:
    """Run every test here with the process clock at UTC+8, so a time read as the host's local time is eight hours off."""
    with pin_host_clock_to_utc_plus_8():
        yield


@pytest.mark.parametrize("value", ["2026-03-31", "20260331", "2026-W14-2"], ids=["extended", "basic", "week-date"])
def test_a_date_alone_names_its_whole_utc_day(value: str) -> None:
    assert parse_time_bound(value) == _DAY_START
    assert parse_time_bound(value, is_upper_bound=True) == _DAY_END


@pytest.mark.parametrize(
    "value",
    ["2026-03-31T00:00:00", "2026-03-31 00:00", "2026-03-31T12:30:00+08:00", "30m", "7d"],
    ids=["midnight", "space-separated", "offset", "minutes", "days"],
)
def test_a_value_with_a_time_or_a_relative_amount_reads_the_same_on_either_side(value: str) -> None:
    lower = parse_time_bound(value)
    upper = parse_time_bound(value, is_upper_bound=True)

    assert lower is not None
    assert upper is not None
    assert abs(upper - lower) < timedelta(seconds=5)  # a relative amount counts back from the moment of the call


@pytest.mark.parametrize("value", [None, "", "   ", "not-a-date", "2026-03", "2026-13-45", "9999y"])
def test_an_unparseable_upper_bound_is_still_dropped(value: str | None) -> None:
    assert parse_time_bound(value, is_upper_bound=True) is None


@pytest.mark.asyncio
async def test_memory_search_tool_searches_through_the_close_of_the_until_day(
    mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
) -> None:
    manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)
    search = AsyncMock(return_value=[])

    with patch.object(MemoryManager, "search", search):
        tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
        await tool.ainvoke({"query": "test", "since": "2026-03-31", "until": "2026-03-31"})

    assert search.call_args.kwargs["since"] == _DAY_START
    assert search.call_args.kwargs["until"] == _DAY_END


@pytest.mark.asyncio
async def test_memory_recall_searches_through_the_close_of_the_until_day() -> None:
    manager = AsyncMock()
    manager.search = AsyncMock(return_value=[])
    manager.last_retrieval_trace = SimpleNamespace(degraded=False)
    server = MemoryMCPServer(manager, server_name="date-only-until")

    await server.mcp.call_tool("memory_recall", {"query": "test", "since": "2026-03-31", "until": "2026-03-31"})

    assert manager.search.call_args.kwargs["since"] == _DAY_START
    assert manager.search.call_args.kwargs["until"] == _DAY_END


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "date_only_until.db"))
    yield s
    await s.close()


@pytest.mark.asyncio
async def test_a_single_day_window_finds_every_fact_saved_that_day_and_no_other(store: SQLiteRelationalStore) -> None:
    saved_at = {
        "day-before": "2026-03-30T23:59:59.999999+00:00",
        "midnight": "2026-03-31T00:00:00+00:00",
        "last-second": "2026-03-31T23:59:59+00:00",
        "last-microsecond": "2026-03-31T23:59:59.999999+00:00",
        "day-after": "2026-04-01T00:00:00+00:00",
    }
    identifiers = {name: str(UUID(int=index, version=4)) for index, name in enumerate(saved_at, start=1)}
    for name, identifier in identifiers.items():
        await store.record_exact_fact(memory_id=name, user_id="u1", content=f"fact {name}", identifiers=[identifier])
    conn = await store._get_connection()
    for name, created_at in saved_at.items():
        await conn.execute("UPDATE exact_fact_identifiers SET created_at = ? WHERE memory_id = ?", (created_at, name))
    await conn.commit()

    hits = await store.search_fts5(
        " ".join(identifiers.values()),
        10,
        since=parse_time_bound("2026-03-31"),
        until=parse_time_bound("2026-03-31", is_upper_bound=True),
    )

    assert sorted(hit.memory.id for hit in hits) == ["last-microsecond", "last-second", "midnight"]
