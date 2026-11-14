"""The zero-hit reply on the MCP surface and as a function: how rules are matched, and which time window ran.

Stored rules are matched as one exact phrase against their trigger and action, so a natural-language query finds
none of them. A client that is only told "nothing found" concludes the rule does not exist and saves a duplicate.
since/until match when a memory was saved, so a memory saved outside an explicit window is invisible to the search;
a client that is not told the window concludes the memory does not exist.

[INPUT]
- toolkits.memory.agent_surface.memory_recall_no_result::no_result_reply, describe_time_window (POS: the zero-hit reply both surfaces share, and its window renderer)
- toolkits.memory.agent_surface.mcp_server::MemoryMCPServer (POS: MCP adapter exposing memory_recall)
- toolkits.memory.agent_surface.memory_recall_budget::DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT (POS: the recall limits the reply quotes)

[POS]
Reply guard for the shared zero-hit reply; the agent tool's side is covered by test_memory_search_zero_hit_reply.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_no_result import (
    describe_time_window,
    no_result_reply,
)
from myrm_agent_harness.toolkits.memory.types import MemoryType

_PLAIN = "No relevant memories found."
_RULES_NOTE = (
    "Stored rules are matched as one exact phrase against their trigger and action: "
    'search one distinctive word, or leave query empty with categories=["rule"] to list rules '
    f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)."
)
_RETRY_ADVICE = "If the memory may have been saved outside this period, retry without since/until."
_MARCH_START = datetime(2026, 3, 1, tzinfo=UTC)
_MARCH_END = datetime(2026, 3, 31, 23, 59, tzinfo=UTC)


def _empty_manager(*, degraded: bool = False) -> AsyncMock:
    manager = AsyncMock()
    manager.search = AsyncMock(return_value=[])
    manager.last_retrieval_trace = SimpleNamespace(degraded=degraded)
    return manager


async def _recall(
    *,
    categories: list[str] | None,
    degraded: bool = False,
    since: str | None = None,
    until: str | None = None,
    manager: AsyncMock | None = None,
) -> str:
    arguments: dict[str, object] = {"query": "summarize code changes in one sentence"}
    if categories is not None:
        arguments["categories"] = categories
    if since is not None:
        arguments["since"] = since
    if until is not None:
        arguments["until"] = until
    server = MemoryMCPServer(manager or _empty_manager(degraded=degraded), server_name="test-memory")
    result = await server.mcp.call_tool("memory_recall", arguments)
    return "".join(str(getattr(block, "text", "")) for block in getattr(result, "content", []))


@pytest.mark.parametrize(
    "categories",
    [None, ["rule"], ["instruction"], ["knowledge", "rule"], ["no-such-category"]],
    ids=["all", "rule", "instruction", "knowledge-and-rule", "unknown-category-searches-all"],
)
async def test_a_recall_that_covers_rules_says_how_rules_are_matched(categories: list[str] | None) -> None:
    reply = await _recall(categories=categories)

    assert reply.startswith(f"{_PLAIN} Stored rules are matched as one exact phrase against their trigger and action")
    assert 'categories=["rule"]' in reply
    assert f"({DEFAULT_RECALL_LIMIT} per call, up to {MAX_RECALL_LIMIT} with limit)" in reply


@pytest.mark.parametrize(
    "categories",
    [["knowledge"], ["claim"], ["event"], ["preference"], ["knowledge", "event"]],
    ids=["knowledge", "claim", "event", "preference", "knowledge-and-event"],
)
async def test_a_recall_that_leaves_rules_out_gets_the_plain_reply(categories: list[str]) -> None:
    assert await _recall(categories=categories) == _PLAIN


async def test_a_timed_out_recall_is_reported_as_a_timeout_not_as_an_empty_one() -> None:
    reply = await _recall(categories=None, degraded=True)

    assert reply == "Memory search timed out. Try a more specific query or retry."


async def test_a_timed_out_recall_under_a_window_is_still_a_timeout() -> None:
    reply = await _recall(categories=["knowledge"], degraded=True, since="30d")

    assert reply == "Memory search timed out. Try a more specific query or retry."


async def test_a_recall_under_an_explicit_window_names_it_before_the_rules_note() -> None:
    reply = await _recall(categories=None, since="2026-03-01", until="2026-03-31T23:59:00+00:00")

    assert reply.startswith(
        f"{_PLAIN} This search was limited to memories saved after 2026-03-01 00:00 UTC and before 2026-03-31 23:59 UTC"
    )
    assert _RETRY_ADVICE in reply
    assert reply.endswith(_RULES_NOTE)


async def test_a_relative_bound_is_named_as_the_instant_the_search_ran_under() -> None:
    manager = _empty_manager()

    reply = await _recall(categories=["knowledge"], since="7d", manager=manager)

    ran_under = manager.search.call_args.kwargs["since"]
    assert f"saved after {ran_under.astimezone(UTC):%Y-%m-%d %H:%M} UTC:" in reply


async def test_a_recall_whose_types_never_read_the_window_gets_the_plain_reply() -> None:
    assert await _recall(categories=["preference"], since="2026-03-01") == _PLAIN
    assert await _recall(categories=["claim"], since="2026-03-01", until="2026-03-31") == _PLAIN


def test_the_reply_depends_only_on_whether_rules_are_in_scope() -> None:
    covering = no_result_reply(None)

    assert covering != _PLAIN
    assert no_result_reply([MemoryType.PROCEDURAL]) == covering
    assert no_result_reply((MemoryType.SEMANTIC, MemoryType.PROCEDURAL)) == covering
    assert no_result_reply([MemoryType.SEMANTIC]) == _PLAIN
    assert no_result_reply((MemoryType.EPISODIC, MemoryType.CLAIM)) == _PLAIN


def test_without_a_window_the_reply_is_the_plain_sentence_or_the_plain_sentence_and_the_rules_note() -> None:
    assert no_result_reply([MemoryType.SEMANTIC]) == _PLAIN
    assert no_result_reply(None) == f"{_PLAIN} {_RULES_NOTE}"


_EACH_BOUND = pytest.mark.parametrize(
    ("since", "until", "period"),
    [
        (_MARCH_START, _MARCH_END, "after 2026-03-01 00:00 UTC and before 2026-03-31 23:59 UTC"),
        (_MARCH_START, None, "after 2026-03-01 00:00 UTC"),
        (None, _MARCH_END, "before 2026-03-31 23:59 UTC"),
    ],
    ids=["both-bounds", "since-only", "until-only"],
)


@_EACH_BOUND
def test_the_window_note_names_each_bound_that_was_given(
    since: datetime | None, until: datetime | None, period: str
) -> None:
    reply = no_result_reply([MemoryType.SEMANTIC], since=since, until=until)

    assert reply == (
        f"{_PLAIN} This search was limited to memories saved {period}: since/until match when a memory was saved, "
        f"not the date it describes. {_RETRY_ADVICE}"
    )


@_EACH_BOUND
def test_a_window_is_described_by_each_bound_that_was_given(
    since: datetime | None, until: datetime | None, period: str
) -> None:
    assert describe_time_window(since, until) == period


def test_a_search_without_a_bound_describes_no_window() -> None:
    assert describe_time_window(None, None) is None


def test_a_bound_with_an_offset_is_named_in_utc() -> None:
    shanghai = timezone(timedelta(hours=8))

    reply = no_result_reply([MemoryType.EPISODIC], since=datetime(2026, 3, 1, 8, 0, tzinfo=shanghai))

    assert "saved after 2026-03-01 00:00 UTC:" in reply


@pytest.mark.parametrize(
    "types",
    [
        None,
        [MemoryType.SEMANTIC],
        [MemoryType.EPISODIC],
        [MemoryType.CONVERSATION],
        [MemoryType.SEMANTIC, MemoryType.PROFILE],
        [MemoryType.EPISODIC, MemoryType.PROCEDURAL],
    ],
    ids=["every-type", "semantic", "episodic", "conversation", "semantic-and-profile", "episodic-and-rules"],
)
def test_a_window_is_named_when_a_searched_type_reads_it(types: list[MemoryType] | None) -> None:
    reply = no_result_reply(types, since=_MARCH_START)

    assert "This search was limited to memories saved after 2026-03-01 00:00 UTC" in reply


@pytest.mark.parametrize(
    "types",
    [
        [MemoryType.PROFILE],
        [MemoryType.PROCEDURAL],
        [MemoryType.CLAIM],
        [MemoryType.PROFILE, MemoryType.PROCEDURAL],
    ],
    ids=["profile", "rules", "claims", "profile-and-rules"],
)
def test_a_window_no_searched_type_reads_is_not_blamed(types: list[MemoryType]) -> None:
    assert no_result_reply(types, since=_MARCH_START, until=_MARCH_END) == no_result_reply(types)
