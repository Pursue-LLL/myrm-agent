"""A date in since/until names the requester's own day: it is read in the zone the request carries.

A model that writes ``since=2026-04-14 until=2026-04-14`` means the user's 14th. Read in UTC, that window is off by the
zone's offset: for a user in Shanghai a memory saved at 01:00 local on the 14th fell outside it, and one saved at 00:30
on the 15th fell inside. The memory and sessions searches get the same two instants, parsed once at the tool entry.

[INPUT]
- core.context_vars::user_timezone_var, scoped_value (POS: the zone the request carries, and a scoped binding of it)
- toolkits.memory.agent_surface.memory_recall_formatting::parse_time_bound (POS: the since/until parser of the recall tools)
- toolkits.memory.agent_surface.memory_agent_tools::create_memory_tools (POS: facade of the agent memory tools)
- toolkits.memory.agent_surface.memory_search_policy::MemorySearchBackends, MemorySearchPolicy (POS: corpus ACL with the optional wiki and sessions backends)
- toolkits.memory.manager::MemoryManager (POS: memory lifecycle manager)
- toolkits.memory.relational::SQLiteRelationalStore (POS: aiosqlite relational store that owns exact-fact search)

[POS]
Contract guard for the zone reading of since/until: at the parser, at the memory_search_tool entry for both corpora, and against a real store.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from myrm_agent_harness.core.context_vars import scoped_value, user_timezone_var
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting import parse_time_bound
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchBackends,
    MemorySearchPolicy,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchResponse
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.relational import SQLiteRelationalStore

SHANGHAI = "Asia/Shanghai"
_SHANGHAI_DAY = (datetime(2026, 4, 13, 16, tzinfo=UTC), datetime(2026, 4, 14, 15, 59, 59, 999999, tzinfo=UTC))
_UTC_DAY = (datetime(2026, 4, 14, tzinfo=UTC), datetime(2026, 4, 14, 23, 59, 59, 999999, tzinfo=UTC))


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(f"{text}+00:00")


@pytest.mark.parametrize(
    ("zone", "day", "start", "end"),
    [
        ("Asia/Shanghai", "2026-04-14", "2026-04-13T16:00:00", "2026-04-14T15:59:59.999999"),
        ("Asia/Kolkata", "2026-04-14", "2026-04-13T18:30:00", "2026-04-14T18:29:59.999999"),
        ("America/Los_Angeles", "2026-04-14", "2026-04-14T07:00:00", "2026-04-15T06:59:59.999999"),
        ("UTC", "2026-04-14", "2026-04-14T00:00:00", "2026-04-14T23:59:59.999999"),
        # Clocks spring forward: a 23-hour day.
        ("America/New_York", "2026-03-08", "2026-03-08T05:00:00", "2026-03-09T03:59:59.999999"),
        # Clocks turn back: a 25-hour day.
        ("America/New_York", "2026-11-01", "2026-11-01T04:00:00", "2026-11-02T04:59:59.999999"),
        # Local midnight does not exist: the day starts at the first instant that does.
        ("America/Havana", "2026-03-08", "2026-03-08T05:00:00", "2026-03-09T03:59:59.999999"),
        # Clocks turn back at midnight, so the last minute occurs twice: the day ends at the later one.
        ("Africa/Cairo", "2026-10-29", "2026-10-28T21:00:00", "2026-10-29T21:59:59.999999"),
    ],
    ids=["shanghai", "kolkata", "los-angeles", "utc", "spring-forward", "fall-back", "midnight-gap", "midnight-repeat"],
)
def test_a_date_names_the_whole_day_in_the_zone(zone: str, day: str, start: str, end: str) -> None:
    assert parse_time_bound(day, zone=zone) == _utc(start)
    assert parse_time_bound(day, is_upper_bound=True, zone=zone) == _utc(end)


@pytest.mark.parametrize("day", ["2026-04-14", "20260414", "2026-W16-2"], ids=["extended", "basic", "week-date"])
def test_every_spelling_of_a_date_reads_in_the_zone(day: str) -> None:
    assert parse_time_bound(day, zone=SHANGHAI) == _SHANGHAI_DAY[0]
    assert parse_time_bound(day, is_upper_bound=True, zone=SHANGHAI) == _SHANGHAI_DAY[1]


@pytest.mark.parametrize("zone", [None, "UTC"])
def test_no_zone_reads_in_utc(zone: str | None) -> None:
    assert parse_time_bound("2026-04-14", zone=zone) == _UTC_DAY[0]
    assert parse_time_bound("2026-04-14", is_upper_bound=True, zone=zone) == _UTC_DAY[1]


@pytest.mark.parametrize("upper", [False, True], ids=["since", "until"])
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-04-14T10:00", "2026-04-14T02:00:00"),
        ("2026-04-14 10:00", "2026-04-14T02:00:00"),
        ("2026-04-14T10:00:00+05:30", "2026-04-14T04:30:00"),
        ("2026-04-14T10:00:00Z", "2026-04-14T10:00:00"),
    ],
    ids=["naive", "space-separated", "offset", "zulu"],
)
def test_a_time_without_an_offset_is_read_in_the_zone_and_one_with_an_offset_keeps_it(
    value: str, expected: str, upper: bool
) -> None:
    assert parse_time_bound(value, is_upper_bound=upper, zone=SHANGHAI) == _utc(expected)


@pytest.mark.parametrize("value", ["30m", "24h", "7d", "2w", "1y"])
def test_a_relative_amount_ignores_the_zone(value: str) -> None:
    zoned = parse_time_bound(value, zone=SHANGHAI)
    unzoned = parse_time_bound(value)

    assert zoned is not None
    assert unzoned is not None
    assert abs(zoned - unzoned) < timedelta(seconds=5)  # both count back from the moment of the call


@pytest.mark.parametrize(
    ("value", "upper", "zone"),
    [("9999-12-31", True, "America/New_York"), ("0001-01-01", False, SHANGHAI)],
    ids=["past-the-last-day", "before-the-first-day"],
)
def test_a_date_pushed_out_of_range_by_the_zone_is_dropped(value: str, upper: bool, zone: str) -> None:
    assert parse_time_bound(value, is_upper_bound=upper, zone=zone) is None


@pytest.fixture
def manager(mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig) -> MemoryManager:
    return MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)


async def _memory_search_bounds(manager: MemoryManager, zone: str | None) -> tuple[datetime | None, datetime | None]:
    """The since/until that memory_search_tool hands the memory search for a request in ``zone``."""
    search = AsyncMock(return_value=[])
    with patch.object(MemoryManager, "search", search), scoped_value(user_timezone_var, zone):
        tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
        await tool.ainvoke({"query": "test", "since": "2026-04-14", "until": "2026-04-14"})
    return search.call_args.kwargs["since"], search.call_args.kwargs["until"]


async def test_memory_search_tool_reads_a_date_window_in_the_requesters_zone(manager: MemoryManager) -> None:
    assert await _memory_search_bounds(manager, SHANGHAI) == _SHANGHAI_DAY


@pytest.mark.parametrize(
    "zone", [None, "", "   ", "Not/AZone", "../etc/passwd"], ids=["none", "empty", "blank", "unknown", "path"]
)
async def test_a_request_without_a_usable_zone_reads_the_window_in_utc(
    manager: MemoryManager, zone: str | None
) -> None:
    assert await _memory_search_bounds(manager, zone) == _UTC_DAY


async def test_the_memory_and_sessions_searches_read_one_window(manager: MemoryManager) -> None:
    provider = AsyncMock()
    provider.search.return_value = ConversationSearchResponse(mode="search")
    search = AsyncMock(return_value=[])
    tools = create_memory_tools(
        manager,
        search_policy=MemorySearchPolicy(allow_sessions=True),
        search_backends=MemorySearchBackends(conversation_provider=provider),
    )
    tool = next(t for t in tools if t.name == "memory_search_tool")

    with patch.object(MemoryManager, "search", search), scoped_value(user_timezone_var, SHANGHAI):
        await tool.ainvoke({"query": "test", "corpus": "all", "since": "2026-04-14", "until": "2026-04-14"})

    request = provider.search.call_args.args[0]
    assert (search.call_args.kwargs["since"], search.call_args.kwargs["until"]) == _SHANGHAI_DAY
    assert (request.since, request.until) == _SHANGHAI_DAY


async def test_an_empty_search_names_the_window_it_ran_in_utc(manager: MemoryManager) -> None:
    with patch.object(MemoryManager, "search", AsyncMock(return_value=[])), scoped_value(user_timezone_var, SHANGHAI):
        tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
        reply = await tool.ainvoke(
            {"query": "test", "categories": ["knowledge"], "since": "2026-04-14", "until": "2026-04-14"}
        )

    assert "saved after 2026-04-13 16:00 UTC and before 2026-04-14 15:59 UTC:" in reply


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteRelationalStore]:
    s = SQLiteRelationalStore(str(tmp_path / "request_zone.db"))
    yield s
    await s.close()


async def test_a_single_day_window_finds_every_fact_saved_that_local_day_and_no_other(
    store: SQLiteRelationalStore,
) -> None:
    saved_at = {
        "evening-before": "2026-04-13T15:59:59+00:00",  # 23:59:59 local on the 13th
        "local-midnight": "2026-04-13T16:00:00+00:00",  # 00:00 local on the 14th
        "small-hours": "2026-04-13T17:00:00+00:00",  # 01:00 local on the 14th: outside the UTC reading of the 14th
        "last-microsecond": "2026-04-14T15:59:59.999999+00:00",  # 23:59:59.999999 local on the 14th
        "next-midnight": "2026-04-14T16:00:00+00:00",  # 00:00 local on the 15th: inside the UTC reading of the 14th
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
        since=parse_time_bound("2026-04-14", zone=SHANGHAI),
        until=parse_time_bound("2026-04-14", is_upper_bound=True, zone=SHANGHAI),
    )

    assert sorted(hit.memory.id for hit in hits) == ["last-microsecond", "local-midnight", "small-hours"]
