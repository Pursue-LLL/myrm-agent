"""Tests for time-range filtering across the memory search pipeline.

Covers:
- Qdrant filter builder datetime-value and datetime-range detection
- _user_filter since/until parameter
- _parse_time_bound relative + ISO 8601 parsing
- the model-visible descriptions teach a month as 30d; every bound they teach parses, a relative one to its duration
- memory_search_tool since/until passthrough (corpus=memory and corpus=sessions)
- MemoryManager.search since/until passthrough
"""

import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.mcpserver import MCPServer

from myrm_agent_harness.toolkits.memory._internal.storage import _user_filter
from myrm_agent_harness.toolkits.memory.agent_surface._memory_agent_tool_descriptions import (
    build_memory_search_tool_description,
)
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.recall_tool import register_recall_tool
from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_formatting import (
    parse_time_bound as _parse_time_bound,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.types import MemoryScope, MemorySearchResult, MemoryType, SemanticMemory
from myrm_agent_harness.toolkits.vector.qdrant.filters import _is_datetime_range, _is_datetime_value


class TestQdrantDatetimeRange:
    """Verify the filter builder's detection of datetime values and datetime ranges."""

    def test_is_datetime_value_iso_string(self) -> None:
        assert _is_datetime_value("2026-04-18T12:00:00") is True

    def test_is_datetime_value_datetime_obj(self) -> None:
        assert _is_datetime_value(datetime(2026, 4, 18, tzinfo=UTC)) is True

    def test_is_datetime_value_integer(self) -> None:
        assert _is_datetime_value(42) is False

    def test_is_datetime_value_plain_string(self) -> None:
        assert _is_datetime_value("hello") is False

    def test_is_datetime_value_empty_string(self) -> None:
        assert _is_datetime_value("") is False

    def test_is_datetime_range_with_iso(self) -> None:
        assert _is_datetime_range({"gte": "2026-01-01T00:00:00", "lte": "2026-12-31T23:59:59"}) is True

    def test_is_datetime_range_with_numbers(self) -> None:
        assert _is_datetime_range({"gte": 0, "lte": 100}) is False

    def test_is_datetime_range_mixed(self) -> None:
        assert _is_datetime_range({"gte": "2026-01-01T00:00:00", "lte": 100}) is True


class TestUserFilter:
    """Verify _user_filter produces correct time-range entries."""

    def test_no_time_filter(self) -> None:
        f = _user_filter()
        assert "created_at" not in f
        assert f["archived"] == {"not": True}

    def test_since_only(self) -> None:
        since = datetime(2026, 4, 1, tzinfo=UTC)
        f = _user_filter(since=since)
        assert "created_at" in f
        time_range = f["created_at"]
        assert isinstance(time_range, dict)
        assert "gte" in time_range
        assert "lte" not in time_range
        assert time_range["gte"] == since.isoformat()

    def test_until_only(self) -> None:
        until = datetime(2026, 4, 30, tzinfo=UTC)
        f = _user_filter(until=until)
        assert "created_at" in f
        time_range = f["created_at"]
        assert isinstance(time_range, dict)
        assert "lte" in time_range
        assert "gte" not in time_range

    def test_since_and_until(self) -> None:
        since = datetime(2026, 4, 1, tzinfo=UTC)
        until = datetime(2026, 4, 30, tzinfo=UTC)
        f = _user_filter(since=since, until=until)
        time_range = f["created_at"]
        assert isinstance(time_range, dict)
        assert "gte" in time_range
        assert "lte" in time_range

    def test_time_filter_with_namespaces(self) -> None:
        since = datetime(2026, 4, 1, tzinfo=UTC)
        f = _user_filter(namespaces=["ns1"], since=since)
        assert f["primary_namespace"] == ["ns1"]
        assert "created_at" in f

    def test_time_filter_preserves_archived_exclusion(self) -> None:
        since = datetime(2026, 4, 1, tzinfo=UTC)
        f = _user_filter(since=since)
        assert f["archived"] == {"not": True}

    def test_time_filter_with_include_archived(self) -> None:
        since = datetime(2026, 4, 1, tzinfo=UTC)
        f = _user_filter(include_archived=True, since=since)
        assert "archived" not in f
        assert "created_at" in f


class TestParseTimeBound:
    """Verify _parse_time_bound handles relative and ISO 8601 inputs."""

    def test_none_returns_none(self) -> None:
        assert _parse_time_bound(None) is None

    def test_empty_returns_none(self) -> None:
        assert _parse_time_bound("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _parse_time_bound("   ") is None

    def test_relative_days(self) -> None:
        result = _parse_time_bound("7d")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert 6.9 < delta.total_seconds() / 86400 < 7.1

    def test_relative_hours(self) -> None:
        result = _parse_time_bound("24h")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert 23.9 < delta.total_seconds() / 3600 < 24.1

    def test_relative_weeks(self) -> None:
        result = _parse_time_bound("2w")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert 13.9 < delta.total_seconds() / 86400 < 14.1

    def test_relative_minutes(self) -> None:
        result = _parse_time_bound("30m")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert 29.9 < delta.total_seconds() / 60 < 30.1

    def test_relative_years(self) -> None:
        result = _parse_time_bound("1y")
        assert result is not None
        delta = datetime.now(UTC) - result
        assert 364 < delta.total_seconds() / 86400 < 366

    def test_iso_with_timezone(self) -> None:
        result = _parse_time_bound("2026-04-01T00:00:00+00:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 1

    def test_iso_naive_gets_utc(self) -> None:
        result = _parse_time_bound("2026-04-01T12:00:00")
        assert result is not None
        assert result.tzinfo == UTC

    @pytest.mark.parametrize(
        ("value", "expected_utc"),
        [
            ("2026-04-17T19:00:00+08:00", datetime(2026, 4, 17, 11, 0)),
            ("2026-04-17T09:00:00-05:00", datetime(2026, 4, 17, 14, 0)),
            ("2026-04-17T01:30:00+08:00", datetime(2026, 4, 16, 17, 30)),
        ],
        ids=["east-of-utc", "west-of-utc", "date-rolls-back"],
    )
    def test_iso_with_offset_is_converted_to_utc(self, value: str, expected_utc: datetime) -> None:
        result = _parse_time_bound(value)
        assert result is not None
        # The bound reaches SQL as its wall-clock digits, so the offset must be gone: `==` alone also holds for the
        # same instant written in any offset.
        assert result.utcoffset() == timedelta(0)
        assert result.replace(tzinfo=None) == expected_utc

    @pytest.mark.parametrize("value", ["9999-12-31T23:59:59-08:00", "0001-01-01T00:00:00+08:00"])
    def test_iso_pushed_out_of_range_by_its_offset_is_unparseable(self, value: str) -> None:
        assert _parse_time_bound(value) is None

    def test_invalid_returns_none(self) -> None:
        assert _parse_time_bound("not-a-date") is None

    def test_case_insensitive(self) -> None:
        result = _parse_time_bound("7D")
        assert result is not None

    def test_with_spaces(self) -> None:
        result = _parse_time_bound("  7d  ")
        assert result is not None


class TestMemoryRecallTimePassing:
    """Verify memory_search_tool(corpus=memory) passes since/until through to MemoryManager.search."""

    @pytest.mark.asyncio
    async def test_recall_passes_since_and_until(
        self, mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
    ) -> None:
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)

        search_mock = AsyncMock(
            return_value=[
                MemorySearchResult(
                    memory=SemanticMemory(
                        content="Test memory", scope=MemoryScope(primary_namespace="global", namespaces=["global"])
                    ),
                    score=0.9,
                    memory_type=MemoryType.SEMANTIC,
                )
            ]
        )

        with patch.object(MemoryManager, "search", search_mock):
            recall_tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
            await recall_tool.ainvoke({"query": "test", "since": "7d", "until": "1d"})

        search_mock.assert_called_once()
        call_kwargs = search_mock.call_args
        assert call_kwargs.kwargs.get("since") is not None
        assert call_kwargs.kwargs.get("until") is not None

    @pytest.mark.asyncio
    async def test_recall_without_time_params(
        self, mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
    ) -> None:
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)

        search_mock = AsyncMock(return_value=[])
        with patch.object(MemoryManager, "search", search_mock):
            recall_tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
            await recall_tool.ainvoke({"query": "test"})

        search_mock.assert_called_once()
        call_kwargs = search_mock.call_args
        assert call_kwargs.kwargs.get("since") is None
        assert call_kwargs.kwargs.get("until") is None

    @pytest.mark.asyncio
    async def test_recall_iso_since(
        self, mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
    ) -> None:
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)

        search_mock = AsyncMock(return_value=[])
        with patch.object(MemoryManager, "search", search_mock):
            recall_tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
            await recall_tool.ainvoke({"query": "test", "since": "2026-04-01T00:00:00"})

        call_kwargs = search_mock.call_args
        since_val = call_kwargs.kwargs.get("since")
        assert since_val is not None
        assert since_val.year == 2026
        assert since_val.month == 4

    @pytest.mark.asyncio
    async def test_recall_invalid_since_ignored(
        self, mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
    ) -> None:
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)

        search_mock = AsyncMock(return_value=[])
        with patch.object(MemoryManager, "search", search_mock):
            recall_tool = next(t for t in create_memory_tools(manager) if t.name == "memory_search_tool")
            await recall_tool.ainvoke({"query": "test", "since": "not-a-date"})

        call_kwargs = search_mock.call_args
        assert call_kwargs.kwargs.get("since") is None


class TestSessionsRecallTimePassing:
    """Verify memory_search_tool(corpus=sessions) hands the parsed since/until to the conversation provider."""

    @pytest.mark.asyncio
    async def test_sessions_search_passes_parsed_since_and_until(
        self, mock_vector_store: AsyncMock, mock_embedding: AsyncMock, memory_config: MemoryConfig
    ) -> None:
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import create_memory_tools
        from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
            MemorySearchBackends,
            MemorySearchPolicy,
        )
        from myrm_agent_harness.toolkits.memory.conversation_search.types import ConversationSearchResponse
        from myrm_agent_harness.toolkits.memory.manager import MemoryManager

        manager = MemoryManager(memory_config, user_id="test_user", vector=mock_vector_store, embedding=mock_embedding)
        provider = AsyncMock()
        provider.search.return_value = ConversationSearchResponse(mode="search")

        tools = create_memory_tools(
            manager,
            search_policy=MemorySearchPolicy(allow_sessions=True),
            search_backends=MemorySearchBackends(conversation_provider=provider),
        )
        search_tool = next(t for t in tools if t.name == "memory_search_tool")
        await search_tool.ainvoke({"query": "test", "corpus": "sessions", "since": "2026-04-10", "until": "2026-04-24"})

        provider.search.assert_awaited_once()
        request = provider.search.call_args.args[0]
        assert request.since == datetime(2026, 4, 10, tzinfo=UTC)
        assert request.until == datetime(2026, 4, 24, tzinfo=UTC)


class TestParseTimeBoundRelativeRange:
    """A relative amount whose instant a datetime cannot hold is unparseable, like an out-of-range ISO bound."""

    @pytest.mark.parametrize(
        "value",
        # 4000 digits overflow the timedelta (OverflowError); 5000 exceed int()'s 4300-digit limit (ValueError).
        ["9999y", "99999y", "999999d", "999999w", "9999999999m", "9" * 4000 + "d", "9" * 5000 + "d"],
        ids=["years", "years-5-digits", "days", "weeks", "minutes", "4000-digits", "5000-digits"],
    )
    def test_amount_beyond_the_datetime_range_is_unparseable(self, value: str) -> None:
        assert _parse_time_bound(value) is None

    @pytest.mark.parametrize("value", ["1000y", "9999d", "99999w", "999999999m", "0d"])
    def test_large_amount_within_the_datetime_range_still_parses(self, value: str) -> None:
        assert _parse_time_bound(value) is not None


# What a model reads from a relative example: ``30m`` is thirty minutes, and a month is written ``30d``.
_EXAMPLE_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}
_RELATIVE_EXAMPLE = re.compile(r"(\d+)([mhdwy])")
# Whitespace and the punctuation between the words of a tip, in English and Chinese; an ASCII colon is left alone
# because an ISO 8601 datetime is one word.
_TIP_WORD_SEPARATORS = re.compile(r"""[\s,、，;；：()（）'"]+""")


async def _mcp_recall_description() -> str:
    mcp = MCPServer("time-bound-examples")
    register_recall_tool(mcp, AsyncMock)  # the resolver only runs when a tool is called, never while listing
    return next(tool.description or "" for tool in await mcp.list_tools() if tool.name == "memory_recall")


def _time_bound_tip(description: str) -> str:
    """The one line of a description that teaches since/until."""
    tips = [line for line in description.splitlines() if "since/until" in line]
    assert len(tips) == 1
    return tips[0]


def _taught_time_bounds(tip: str) -> list[str]:
    """The words of a tip that carry a digit: each is a time bound the model is shown.

    "ISO 8601" names a format rather than a bound, so it is not one of them.
    """
    words = _TIP_WORD_SEPARATORS.split(tip.replace("ISO 8601", " "))
    return [word for word in words if any(char.isdigit() for char in word)]


class TestRelativeExamplesTaughtToTheModel:
    """Every since/until bound a model is shown parses, a relative one means what it says, and a month is written 30d.

    The bounds sit in three model-visible texts while the unit table lives in ``parse_time_bound``; nothing else
    ties the two together, so an edit to either side alone silently teaches the model a wrong or ignored window.
    """

    @pytest.mark.asyncio
    async def test_examples_parse_to_the_duration_they_name(self) -> None:
        descriptions = {
            "memory_search_tool en": build_memory_search_tool_description(MemorySearchPolicy(), locale="en"),
            "memory_search_tool zh": build_memory_search_tool_description(MemorySearchPolicy(), locale="zh"),
            "memory_recall": await _mcp_recall_description(),
        }
        for surface, description in descriptions.items():
            taught = _taught_time_bounds(_time_bound_tip(description))
            for word in taught:
                bound = _parse_time_bound(word)
                assert bound is not None, f"{surface}: {word} is unparseable"
                relative = _RELATIVE_EXAMPLE.fullmatch(word)
                if relative is None:
                    continue
                amount, unit = relative.groups()
                age_seconds = (datetime.now(UTC) - bound).total_seconds()
                assert age_seconds == pytest.approx(int(amount) * _EXAMPLE_UNIT_SECONDS[unit], abs=5), (
                    f"{surface}: {word} parses to {age_seconds:.0f} seconds"
                )
            assert "30d" in taught, f"{surface} must teach a month as 30d"
