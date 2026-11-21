"""`search_sessions_corpus` maps `memory_search_tool(corpus=sessions)` arguments onto the provider request, words an
empty reply that ran under an explicit since/until window, and writes the hit times in the requester's zone."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_execution import (
    search_sessions_corpus,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchBackends,
)
from myrm_agent_harness.toolkits.memory.conversation_search.types import (
    MAX_CONVERSATION_SEARCH_LIMIT,
    ConversationSearchHit,
    ConversationSearchRequest,
    ConversationSearchResponse,
)


class _RecordingProvider:
    """Conversation provider double that records every request it receives."""

    def __init__(self, response: ConversationSearchResponse) -> None:
        self._response = response
        self.requests: list[ConversationSearchRequest] = []

    async def search(self, request: ConversationSearchRequest) -> ConversationSearchResponse:
        self.requests.append(request)
        return self._response


def _recent_response() -> ConversationSearchResponse:
    return ConversationSearchResponse(
        mode="recent",
        hits=[
            ConversationSearchHit(
                conversation_id="chat-recent",
                title="Recent plan",
                snippet="Recent deployment plan",
                summary="We discussed a local Tauri deployment.",
                score=0.9,
                source="recent",
            )
        ],
    )


def _empty_search_response() -> ConversationSearchResponse:
    return ConversationSearchResponse(mode="search", query="deployment", hits=[])


def _timed_response() -> ConversationSearchResponse:
    return ConversationSearchResponse(
        mode="search",
        query="deployment",
        hits=[
            ConversationSearchHit(
                conversation_id="chat-timed",
                title="Deployment plan",
                snippet="Deployment plan",
                score=0.9,
                updated_at=datetime(2026, 4, 2, 17, 30, 15, 250_000, tzinfo=UTC),
            )
        ],
    )


async def _search(
    provider: _RecordingProvider,
    *,
    query: str,
    limit: int = 5,
    since: datetime | None = None,
    until: datetime | None = None,
    expand_conversation_id: str | None = None,
    expand_message_id: str | None = None,
    expand_window: int = 5,
    zone: str | None = None,
) -> str | dict[str, object]:
    return await search_sessions_corpus(
        MemorySearchBackends(conversation_provider=provider),
        query=query,
        limit=limit,
        since=since,
        until=until,
        expand_conversation_id=expand_conversation_id,
        expand_message_id=expand_message_id,
        expand_window=expand_window,
        zone=zone,
    )


async def test_star_query_routes_to_recent_mode() -> None:
    provider = _RecordingProvider(_recent_response())

    result = await _search(provider, query="*")

    assert isinstance(result, dict)
    assert "Recent conversations" in str(result.get("content", ""))
    assert provider.requests[0].query == ""
    assert provider.requests[0].mode == "recent"


async def test_blank_query_routes_to_recent_mode() -> None:
    provider = _RecordingProvider(_recent_response())

    await _search(provider, query="   ")

    assert provider.requests[0].query == ""
    assert provider.requests[0].mode == "recent"


async def test_text_query_stays_in_search_mode_and_clamps_the_limit() -> None:
    provider = _RecordingProvider(_empty_search_response())

    await _search(provider, query="deployment", limit=500)

    request = provider.requests[0]
    assert request.query == "deployment"
    assert request.mode is None
    assert request.limit == MAX_CONVERSATION_SEARCH_LIMIT
    assert request.scope == "current_agent"


async def test_expand_arguments_are_forwarded_to_the_provider() -> None:
    provider = _RecordingProvider(_empty_search_response())

    await _search(
        provider,
        query="",
        expand_conversation_id="chat-2",
        expand_message_id="msg-2",
        expand_window=8,
    )

    request = provider.requests[0]
    assert request.expand_conversation_id == "chat-2"
    assert request.expand_message_id == "msg-2"
    assert request.expand_window == 8


async def test_an_empty_search_under_a_window_names_it_and_still_sends_it_to_the_provider() -> None:
    since, until = datetime(2026, 12, 10, tzinfo=UTC), datetime(2026, 12, 24, tzinfo=UTC)
    provider = _RecordingProvider(_empty_search_response())

    result = await _search(provider, query="deployment", since=since, until=until)

    assert (provider.requests[0].since, provider.requests[0].until) == (since, until)
    assert isinstance(result, dict)
    assert str(result["content"]).endswith(
        "This search was limited to conversations whose last message was sent after 2026-12-10 00:00 UTC and before "
        "2026-12-24 00:00 UTC: other conversations are not returned, even if part of them falls inside that period. "
        "If what you need may be outside that period, retry without since/until."
    )


@pytest.mark.parametrize(
    ("zone", "written"),
    [(None, "2026-04-02T17:30:15.250000+00:00"), ("Asia/Shanghai", "2026-04-03T01:30:15.250000+08:00")],
    ids=["utc", "requester-zone"],
)
async def test_a_hit_time_is_written_in_the_zone_the_search_is_given(zone: str | None, written: str) -> None:
    result = await _search(_RecordingProvider(_timed_response()), query="deployment", zone=zone)

    assert isinstance(result, dict)
    assert f", {written})" in str(result["content"])


async def test_an_expand_request_is_not_blamed_on_the_window() -> None:
    refusal = "No visible messages found for the requested expand window."
    provider = _RecordingProvider(ConversationSearchResponse(mode="search", query="", hits=[], rejected_reason=refusal))

    result = await _search(
        provider,
        query="",
        since=datetime(2026, 12, 10, tzinfo=UTC),
        until=datetime(2026, 12, 24, tzinfo=UTC),
        expand_conversation_id="chat-2",
        expand_message_id="msg-2",
    )

    assert isinstance(result, dict)
    assert result["content"] == refusal


async def test_missing_provider_reports_unavailable() -> None:
    result = await search_sessions_corpus(
        MemorySearchBackends(),
        query="deployment",
        limit=5,
        since=None,
        until=None,
    )

    assert result == "Conversation history search is not available."
