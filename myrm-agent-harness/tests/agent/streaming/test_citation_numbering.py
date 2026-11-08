"""Citation numbers across the tool calls of one run: the number a tool prints is the index of the card the stream issues.

The real tools run on canned provider results. The run's ``SourceTracker`` is bound the way the stream executor binds
it, and every tool result's ``metadata.sources`` become cards the way the stream handlers issue them. A graph tool node
shows that the binding made in the streaming task reaches async and sync tool bodies.

[POS]
Chain-level tests of citation numbering: tool -> printed ``【n】`` -> source normalization -> cards, and the run binding
that hands the tools their numbering. The tracker's own rules are covered in test_source_tracker_numbering.py.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.agent.streaming.stream_executor import StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.core.context_vars import SourceIndexer, scoped_value, source_indexer_var
from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools
from myrm_agent_harness.toolkits.web_fetch.web_fetch_agent_tools import _fetch_full_content
from myrm_agent_harness.toolkits.web_search.processing.citation_resolver import strip_tracking_parameters
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, WebSearcher
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import create_web_search_tool
from myrm_agent_harness.utils.url_utils import url_dedup_key


def _page(url: str) -> Document:
    return Document(
        page_content=f"text of {url}", metadata={"url": url, "title": f"Title of {url}", "snippet": f"About {url}"}
    )


def _provider_returns(results: dict[str, list[str]]) -> AbstractContextManager[object]:
    """Answer each question with the pages listed for it, as the provider search would."""

    async def multi_query_parallel_search(
        _self: WebSearcher, queries: list[str], _results_per_query: int, time_range: str | None = None
    ) -> list[tuple[str, list[Document], Exception | None]]:
        assert time_range is None
        return [(query, [_page(url) for url in results[query]], None) for query in queries]

    return patch.object(WebSearcher, "multi_query_parallel_search", multi_query_parallel_search)


async def _search(question: str) -> dict[str, object]:
    search_tool = create_web_search_tool(SearchServiceConfig(search_service="tavily", api_key="key"))
    result = await search_tool.ainvoke({"questions": [question], "reason": ""})
    assert isinstance(result, dict)
    return result


def _labels(result: dict[str, object]) -> dict[str, int]:
    """URL -> number, as the model reads them in the tool's content."""
    content = result["content"]
    assert isinstance(content, str)
    return {url: int(number) for number, url in re.findall(r"【(\d+)】 URL: (\S+)", content)}


class _Stream:
    """What the stream does with a tool result: issue a card for each new source."""

    def __init__(self) -> None:
        self.tracker = SourceTracker()
        self.cards: dict[int, dict[str, object]] = {}

    def receive(self, result: dict[str, object]) -> None:
        # LangChain hands the tool's dict to the stream as JSON.
        metadata = json.loads(json.dumps(result["metadata"]))
        for card in self.tracker.add_batch(metadata["sources"]):
            index = card["index"]
            assert isinstance(index, int)
            assert index not in self.cards
            self.cards[index] = card

    def assert_labels_name_their_cards(self, labels: dict[str, int]) -> None:
        for url, number in labels.items():
            card = self.cards.get(number)
            assert card is not None, f"{number} is printed for {url} and has no card"
            card_url = card["url"]
            assert isinstance(card_url, str)
            assert _key(card_url) == _key(url), f"{number} is printed for {url}, its card is {card_url}"


def _key(url: str) -> str:
    return url_dedup_key(strip_tracking_parameters(url), keep_fragment=True)


@pytest.mark.asyncio
async def test_numbers_printed_by_two_searches_and_a_fetch_name_the_cards_of_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_crawl_many(
        urls: Sequence[str], *, max_chars: int = 0, **_kwargs: object
    ) -> tuple[list[tuple[str, Document]], list[tuple[str, None]]]:
        return [(url, _page(url)) for url in urls], []

    monkeypatch.setattr(web_fetch_tools, "crawl_many", fake_crawl_many)
    stream = _Stream()
    results = {
        "alpha": ["https://a.test/x", "https://b.test/y?utm_source=rss"],
        "beta": ["https://c.test/z", "https://b.test/y", "https://a.test/x/"],
    }

    with scoped_value(source_indexer_var, stream.tracker.index_for), _provider_returns(results):
        first = await _search("alpha")
        stream.receive(first)
        second = await _search("beta")
        stream.receive(second)
        fetched = await _fetch_full_content(["https://d.test/w", "https://c.test/z"])
        stream.receive(fetched)

    first_labels, second_labels, fetched_labels = _labels(first), _labels(second), _labels(fetched)
    assert len(first_labels) == 2
    assert len(second_labels) == 3
    assert len(fetched_labels) == 2
    for labels in (first_labels, second_labels, fetched_labels):
        stream.assert_labels_name_their_cards(labels)

    # A page keeps its number across calls, whichever spelling the call shows it under.
    assert second_labels["https://a.test/x/"] == first_labels["https://a.test/x"]
    assert second_labels["https://b.test/y"] == first_labels["https://b.test/y?utm_source=rss"]
    assert fetched_labels["https://c.test/z"] == second_labels["https://c.test/z"]
    assert len(stream.cards) == 4


@pytest.mark.asyncio
async def test_without_a_bound_run_each_search_numbers_from_one() -> None:
    with _provider_returns({"alpha": ["https://a.test/x"], "beta": ["https://c.test/z"]}):
        first, second = await _search("alpha"), await _search("beta")

    assert _labels(first) == {"https://a.test/x": 1}
    assert _labels(second) == {"https://c.test/z": 1}


def _executor_streaming(tracker: SourceTracker, seen: list[SourceIndexer | None]) -> StreamExecutor:
    """An executor whose graph, once streamed, records the source numbering the tools running in it would get."""

    async def fake_astream(
        *_args: object, **_kwargs: object
    ) -> AsyncIterator[tuple[str, tuple[AIMessage, dict[str, list[str]]]]]:
        seen.append(source_indexer_var.get())
        yield ("messages", (AIMessage(content="done"), {"tags": []}))

    ctx = StreamContext(
        agent=MagicMock(),
        agent_input={"messages": [HumanMessage(content="hi")]},
        merged_context={"locale": "en"},
        run_config={},
        stats=AgentRunStatistics(),
        message_id="citation_numbering",
        cancel_token=None,
        steering_token=None,
        source_tracker=tracker,
        output_queue=asyncio.Queue(),
    )
    ctx.agent.astream = fake_astream
    return StreamExecutor(ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock())


@pytest.mark.asyncio
async def test_a_run_numbers_the_sources_of_its_tools_with_its_own_tracker() -> None:
    tracker, seen = SourceTracker(), []

    # The runtime streams every run in a task of its own.
    await asyncio.create_task(_executor_streaming(tracker, seen).execute())

    assert seen == [tracker.index_for]
    assert source_indexer_var.get() is None


@pytest.mark.asyncio
async def test_a_child_run_numbers_with_its_own_tracker_and_leaves_the_parents_alone() -> None:
    parent, child = SourceTracker(), SourceTracker()
    seen: list[SourceIndexer | None] = []

    with scoped_value(source_indexer_var, parent.index_for):
        # A delegated run executes inside the parent's tool call, in a task of its own.
        await asyncio.create_task(_executor_streaming(child, seen).execute())
        assert source_indexer_var.get() == parent.index_for

    assert seen == [child.index_for]


@pytest.mark.asyncio
async def test_tool_bodies_run_by_a_graph_tool_node_get_the_binding_of_the_streaming_task() -> None:
    """The tools of a run are executed by a graph tool node while the task streams: async and sync bodies alike."""
    seen: dict[str, SourceIndexer | None] = {}

    @tool
    async def async_tool(text: str) -> str:
        """Record the source numbering an async tool body gets."""
        seen["async"] = source_indexer_var.get()
        return text

    @tool
    def sync_tool(text: str) -> str:
        """Record the source numbering a sync tool body gets."""
        seen["sync"] = source_indexer_var.get()
        return text

    def call_both_tools(_state: MessagesState) -> dict[str, list[AIMessage]]:
        calls = [
            ToolCall(name="async_tool", args={"text": "a"}, id="call-async"),
            ToolCall(name="sync_tool", args={"text": "b"}, id="call-sync"),
        ]
        return {"messages": [AIMessage(content="", tool_calls=calls)]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_both_tools)
    graph.add_node("tools", ToolNode([async_tool, sync_tool]))
    graph.add_edge(START, "model")
    graph.add_edge("model", "tools")
    graph.add_edge("tools", END)
    app = graph.compile()
    tracker = SourceTracker()

    async def stream() -> None:
        with scoped_value(source_indexer_var, tracker.index_for):
            async for _update in app.astream({"messages": [HumanMessage(content="hi")]}, stream_mode="updates"):
                pass

    await asyncio.create_task(stream())

    assert seen == {"async": tracker.index_for, "sync": tracker.index_for}
