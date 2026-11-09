"""Citation sources on their way from a tool to the stream: tool, LangChain message, interceptor, SSE events.

Every producer returns ``{"content", "metadata": {"sources", ...}}``. Across LangChain's stringification, the tool
interceptor and the stream handlers, the model must stop reading the sources list while the stream still emits the
same ``reviewing_sources`` and ``sources`` events for it.

[POS]
Chain-level tests of tool-sources hoisting, one case per kind of producer, and of the numbers the stored sources carry.
The hoisting and stamping rules themselves are covered in test_tool_sources_hoisting.py.
"""

from __future__ import annotations

import base64
import copy
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.tools import tool
from langchain_core.messages import ToolCall, ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.meta_tools.bash._executor.mcp_citation_handler import MCPMetadataExtractor
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import _tool_interceptor_middleware_inner
from myrm_agent_harness.agent.middlewares.tooling.tool_sources_hoisting import TOOL_SOURCES_KWARG
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.core.context_vars import scoped_value, source_indexer_var
from myrm_agent_harness.toolkits.browser.tools.navigate import create_navigate_tool
from myrm_agent_harness.toolkits.memory.agent_surface.tool_result_sources import pack_tool_result_with_sources
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import _full_content_result
from myrm_agent_harness.toolkits.web_search import engine as engine_mod
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import create_web_search_tool

_INTERCEPTOR = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware"
_MESSAGE_ID = "msg_1"
_MCP_NONCE = "0123456789abcdef0123456789abcdef"

WEB_SOURCES: list[dict[str, object]] = [
    {"type": "web_search", "url": "https://a.test/post", "title": "Post A", "snippet": "alpha 中文"},
    {"type": "web_search", "url": "https://b.test/post", "title": "Post B", "snippet": "beta"},
]


# --- Producers: each returns the dict a tool of that kind returns --------------------------------------------------


async def _web_search() -> dict[str, object]:
    search_tool = create_web_search_tool(SearchServiceConfig(search_service="tavily", api_key="key"))
    with patch.object(engine_mod.WebSearchTools, "fast_search_with_questions", new_callable=AsyncMock) as engine:
        engine.return_value = (copy.deepcopy(WEB_SOURCES), "【1】 alpha 中文\n【2】 beta")
        result = await search_tool.ainvoke({"questions": ["q"], "reason": ""})
    assert isinstance(result, dict)
    return result


async def _browser_navigate() -> dict[str, object]:
    page = MagicMock()
    page.url = "https://example.com"
    page.title = AsyncMock(return_value="Example Page")
    session = MagicMock()
    session.navigate = AsyncMock(return_value="Navigated to Example Page (https://example.com, status=200)")
    session.get_active_page = MagicMock(return_value=page)
    result = await create_navigate_tool(session).ainvoke({"url": "https://example.com"})
    assert isinstance(result, dict)
    return result


async def _memory_search() -> dict[str, object]:
    return pack_tool_result_with_sources("remembered note", [{"type": "memory", "title": "Note", "source_key": "n1"}])


async def _wiki_query() -> dict[str, object]:
    sources: list[dict[str, object]] = [{"type": "wiki", "filename": "test-concept", "title": "Test Concept"}]
    return {"content": "<<<UNTRUSTED_DATA>>>evidence<<<END_UNTRUSTED_DATA>>>", "metadata": {"sources": sources}}


async def _web_fetch_full_content() -> dict[str, object]:
    return _full_content_result("page text", sources=copy.deepcopy(WEB_SOURCES[:1]), truncated=False, raw_chars=9)


async def _bash_with_mcp_calls() -> dict[str, object]:
    record = {"s": "mcp_demo_skill", "t": "lookup", "r": "result text 中文"}
    encoded = base64.b64encode(json.dumps(record, ensure_ascii=False).encode()).decode()
    marker = f"__MCP_DATA__{_MCP_NONCE}{encoded}__END__{_MCP_NONCE}"
    stdout, metadata = MCPMetadataExtractor().extract_metadata(f"[RESULT] done\n{marker}\n", _MCP_NONCE)
    return {"content": stdout, "metadata": metadata}


@dataclass(frozen=True)
class _Producer:
    build: Callable[[], Awaitable[dict[str, object]]]
    # True when nothing but ``content`` is left of the envelope once its sources are lifted out.
    leaves_only_content: bool


PRODUCERS: dict[str, _Producer] = {
    "web_search": _Producer(_web_search, leaves_only_content=True),
    "browser_navigate": _Producer(_browser_navigate, leaves_only_content=True),
    "memory_search": _Producer(_memory_search, leaves_only_content=True),
    "wiki_query": _Producer(_wiki_query, leaves_only_content=True),
    "web_fetch_full_content": _Producer(_web_fetch_full_content, leaves_only_content=False),
    "bash_with_mcp_calls": _Producer(_bash_with_mcp_calls, leaves_only_content=False),
}


# --- The chain ---------------------------------------------------------------------------------------------------


async def _langchain_message(payload: dict[str, object]) -> ToolMessage:
    """The ToolMessage LangChain builds from a tool's dict result: the dict is JSON-serialised into its content."""

    @tool("producer_tool")
    async def producer_tool() -> dict[str, object]:
        """Return a canned result."""
        return payload

    message = await producer_tool.ainvoke(ToolCall(name="producer_tool", args={}, id="call_1", type="tool_call"))
    assert isinstance(message, ToolMessage)
    return message


async def _intercepted(
    message: ToolMessage, guard_output: ToolMessage | None = None
) -> tuple[ToolMessage | Command[object], AsyncMock]:
    """Run the interceptor on a tool that returned ``message``; the post-call guards return ``guard_output``."""
    request = MagicMock()
    request.tool_call = {"name": "producer_tool", "args": {}, "id": "call_1"}

    async def _handler(_request: object) -> ToolMessage:
        raise AssertionError("execute_with_retry is patched; the handler must not run")

    post_guards = AsyncMock(side_effect=lambda result, *_: guard_output or result)
    with (
        patch(f"{_INTERCEPTOR}.run_pre_call_guards", AsyncMock(return_value=MagicMock())),
        patch(f"{_INTERCEPTOR}.execute_with_retry", AsyncMock(return_value=message)),
        patch(f"{_INTERCEPTOR}.run_post_call_guards", post_guards),
        patch(f"{_INTERCEPTOR}.get_token_tracker", return_value=None),
        patch(f"{_INTERCEPTOR}.emit_tool_heartbeat", AsyncMock()),
        patch("myrm_agent_harness.agent.middlewares._session_context.get_allowed_domains_map", return_value={}),
    ):
        return await _tool_interceptor_middleware_inner(request, _handler), post_guards


async def _stream_events(message: ToolMessage | Command[object]) -> list[dict[str, object]]:
    updates: dict[str, dict[str, object]] = {"tools": {"messages": [message]}}
    stream = process_updates_chunk(updates, AgentRunStatistics(), _MESSAGE_ID, source_tracker=SourceTracker())
    return [event async for event in stream]


def _citation_events(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    """What the frontend receives for a sources list: its numbered, de-duplicated entries, as a step and as citations."""
    numbered = SourceTracker().add_batch(copy.deepcopy(sources))
    return [
        {
            "type": AgentEventType.TASKS_STEPS.value,
            "step_key": "reviewing_sources",
            "tool_name": None,
            "count": len(numbered),
            "data": numbered,
            "messageId": _MESSAGE_ID,
        },
        {"type": AgentEventType.SOURCES.value, "data": numbered, "messageId": _MESSAGE_ID},
    ]


def _metadata_of(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload["metadata"]
    assert isinstance(metadata, dict)
    return metadata


def _sources_of(payload: dict[str, object]) -> list[dict[str, object]]:
    sources = _metadata_of(payload)["sources"]
    assert isinstance(sources, list)
    return sources


class TestFromToolToStream:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("producer", PRODUCERS.values(), ids=list(PRODUCERS))
    async def test_the_model_reads_the_result_without_its_sources(self, producer: _Producer) -> None:
        payload = await producer.build()
        message = await _langchain_message(payload)
        assert '"sources"' in str(message.content)

        result, _ = await _intercepted(message)

        assert isinstance(result, ToolMessage)
        assert len(str(result.content)) < len(str(message.content))
        if producer.leaves_only_content:
            assert result.content == payload["content"]
            return
        remaining = json.loads(str(result.content))
        assert remaining["content"] == payload["content"]
        assert remaining["metadata"] == {k: v for k, v in _metadata_of(payload).items() if k != "sources"}
        assert {k: v for k, v in remaining.items() if k != "metadata"} == {
            k: v for k, v in payload.items() if k != "metadata"
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("producer", PRODUCERS.values(), ids=list(PRODUCERS))
    async def test_the_stream_cites_the_same_sources(self, producer: _Producer) -> None:
        payload = await producer.build()
        result, _ = await _intercepted(await _langchain_message(payload))

        assert isinstance(result, ToolMessage)
        assert result.additional_kwargs[TOOL_SOURCES_KWARG] == _sources_of(payload)
        assert await _stream_events(result) == _citation_events(_sources_of(payload))

    @pytest.mark.asyncio
    async def test_the_post_call_guards_see_the_whole_result(self) -> None:
        message = await _langchain_message(await _web_search())

        _, post_guards = await _intercepted(message)

        assert post_guards.await_args is not None
        assert post_guards.await_args.args[0] is message
        assert '"sources"' in str(message.content)

    @pytest.mark.asyncio
    async def test_sources_are_lifted_from_the_result_the_guards_return(self) -> None:
        message = await _langchain_message(await _web_search())
        redacted = message.model_copy(update={"content": str(message.content).replace("alpha", "[REDACTED]")})

        result, _ = await _intercepted(message, guard_output=redacted)

        assert isinstance(result, ToolMessage)
        assert result.additional_kwargs[TOOL_SOURCES_KWARG][0]["snippet"] == "[REDACTED] 中文"
        assert "alpha" not in str(result.content)

    @pytest.mark.asyncio
    async def test_an_envelope_a_guard_appended_text_to_is_passed_through_whole(self) -> None:
        message = await _langchain_message(await _web_search())
        appended = message.model_copy(update={"content": f"{message.content}\n\nLoop warning: change approach"})

        result, _ = await _intercepted(message, guard_output=appended)

        assert result is appended


class TestTheStoredSourcesCarryTheRunsNumbers:
    """What the checkpoint keeps of a tool call records the numbers the model read, which are the cards' indexes."""

    @staticmethod
    async def _cards(result: ToolMessage | Command[object], tracker: SourceTracker) -> list[dict[str, object]]:
        updates: dict[str, dict[str, object]] = {"tools": {"messages": [result]}}
        stream = process_updates_chunk(updates, AgentRunStatistics(), _MESSAGE_ID, source_tracker=tracker)
        events = [event async for event in stream]
        sources_event = next(event for event in events if event["type"] == AgentEventType.SOURCES.value)
        cards = sources_event["data"]
        assert isinstance(cards, list)
        return cards

    @pytest.mark.asyncio
    async def test_the_stored_number_of_a_source_the_tool_numbered_is_the_number_it_printed(self) -> None:
        tracker = SourceTracker()
        message = await _langchain_message(await _web_search())
        # The tool numbered the second source first, as a result that orders its text by relevance does.
        printed = {"b": tracker.index_for(WEB_SOURCES[1]), "a": tracker.index_for(WEB_SOURCES[0])}

        with scoped_value(source_indexer_var, tracker.index_for):
            result, _ = await _intercepted(message)

        assert isinstance(result, ToolMessage)
        stored = result.additional_kwargs[TOOL_SOURCES_KWARG]
        assert [(source["url"], source["index"]) for source in stored] == [
            ("https://a.test/post", printed["a"]),
            ("https://b.test/post", printed["b"]),
        ]

    @pytest.mark.asyncio
    async def test_each_stored_number_is_the_index_of_the_card_the_stream_issues(self) -> None:
        tracker = SourceTracker()
        message = await _langchain_message(await _web_search())

        with scoped_value(source_indexer_var, tracker.index_for):
            result, _ = await _intercepted(message)
        assert isinstance(result, ToolMessage)
        cards = await self._cards(result, tracker)

        stored = result.additional_kwargs[TOOL_SOURCES_KWARG]
        assert [(card["url"], card["index"]) for card in cards] == [(s["url"], s["index"]) for s in stored]

    @pytest.mark.asyncio
    async def test_the_text_the_model_reads_is_the_same_with_and_without_the_numbers(self) -> None:
        message = await _langchain_message(await _web_search())

        plain, _ = await _intercepted(message)
        with scoped_value(source_indexer_var, SourceTracker().index_for):
            numbered, _ = await _intercepted(message)

        assert isinstance(plain, ToolMessage)
        assert isinstance(numbered, ToolMessage)
        assert numbered.content == plain.content

    @pytest.mark.asyncio
    async def test_a_run_that_numbers_nothing_stores_the_sources_as_the_tool_returned_them(self) -> None:
        payload = await _web_search()

        result, _ = await _intercepted(await _langchain_message(payload))

        assert isinstance(result, ToolMessage)
        assert all("index" not in source for source in result.additional_kwargs[TOOL_SOURCES_KWARG])
