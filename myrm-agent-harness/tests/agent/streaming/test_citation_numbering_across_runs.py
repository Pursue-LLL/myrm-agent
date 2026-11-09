"""Citation numbers across the runs of one thread: a number the model read names one page for the whole thread.

A thread continues in a run of its own after an approval pause and in the next turn. Every run builds a fresh
``SourceTracker``; the numbers the model read in the earlier runs are still in its context, and the cards of the
earlier runs are still on screen, so the later run has to number on from them.

The run is the real one: the ``create_agent`` loop with the tool interceptor, the real web search tool over canned
provider results, ``StreamExecutor.execute()`` with the stream handlers, and a checkpointer holding the thread. Only
the provider and the model are scripted.

[POS]
End-to-end tests of the numbering of a thread over several runs: tool -> printed ``【n】`` -> stored tool message ->
next run's tracker -> cards. The tracker's and the restore step's own rules are covered in
test_source_tracker_numbering.py and test_source_numbering.py.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from unittest.mock import MagicMock, patch

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import BaseTool, tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt

from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import tool_interceptor_middleware
from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker
from myrm_agent_harness.agent.streaming.types import AgentEventType, AgentStreamEvent
from myrm_agent_harness.toolkits.web_search.processing.citation_resolver import strip_tracking_parameters
from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig, WebSearcher
from myrm_agent_harness.toolkits.web_search.web_search_agent_tools import create_web_search_tool
from myrm_agent_harness.utils.url_utils import url_dedup_key

from .scripted_agent import (
    THREAD_ID,
    TRACKER_PATH,
    RecordingCompactor,
    ScriptedModel,
    Turn,
    make_context,
    make_executor,
)

READ_ACCESS_LOGGER = "myrm_agent_harness.runtime.checkpointing.read_access"
THREAD_CONFIG: RunnableConfig = {"configurable": {"thread_id": THREAD_ID}}

# Page "P2" is returned under a tracking parameter by both searches.
P1, P2, P3, P4, P5 = (f"https://p{n}.test/page" for n in range(1, 6))
P2_TRACKED = f"{P2}?utm_source=feed"
RESULTS = {"first": [P1, P2_TRACKED, P3], "second": [P4, P2_TRACKED, P5]}

Step = tuple[str, str] | None
"""One model reply: ``("search", question)``, ``("publish", title)`` (a call the approval gate pauses), or ``None``
for the final answer."""

Handler = Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]]


@tool
def publish_report(title: str) -> str:
    """Publish a report."""
    return f"published {title}"


@wrap_tool_call
async def approval_gate(request: ToolCallRequest, handler: Handler) -> ToolMessage | Command[object]:
    """Stands in for the approval middleware: the run pauses before the gated tool executes."""
    if request.tool_call["name"] == "publish_report":
        interrupt({"action": "publish_report"})
    return await handler(request)


def _provider_returns() -> AbstractContextManager[object]:
    async def multi_query_parallel_search(
        _self: WebSearcher, queries: list[str], _results_per_query: int, time_range: str | None = None
    ) -> list[tuple[str, list[Document], Exception | None]]:
        assert time_range is None
        return [
            (
                query,
                [
                    Document(page_content=f"text of {url}", metadata={"url": url, "title": url})
                    for url in RESULTS[query]
                ],
                None,
            )
            for query in queries
        ]

    return patch.object(WebSearcher, "multi_query_parallel_search", multi_query_parallel_search)


class _Thread:
    """One conversation thread: the agent over its checkpointer, and the cards each run of it issued."""

    def __init__(self, steps: list[Step], checkpointer: InMemorySaver | None = None) -> None:
        search = create_web_search_tool(SearchServiceConfig(search_service="tavily", api_key="key"))
        tools: list[BaseTool] = [search, publish_report]

        def turn(number: int, step: Step) -> Turn:
            if step is None:
                return AIMessage(content="Done."), "stop"
            kind, text = step
            call = (
                {"name": search.name, "args": {"questions": [text], "reason": ""}, "id": f"call_{number}"}
                if kind == "search"
                else {"name": "publish_report", "args": {"title": text}, "id": f"call_{number}"}
            )
            return AIMessage(content="", tool_calls=[call]), "tool_calls"

        self.model = ScriptedModel(
            turns=[turn(number, step) for number, step in enumerate(steps)],
            tracker=MagicMock(last_finish_reason=None, usage=None, total_cost_usd=0.0),
        )
        self.agent = create_agent(
            self.model,
            tools=tools,
            middleware=[approval_gate, tool_interceptor_middleware],
            checkpointer=checkpointer or InMemorySaver(),
        )
        self.cards: list[tuple[int, str]] = []

    async def run(self, agent_input: dict[str, list[HumanMessage]] | Command[str]) -> None:
        """One run, built the way the runtime builds it: a fresh tracker over the thread's checkpointer."""
        ctx = make_context(self.agent, agent_input, thread_id=THREAD_ID)
        ctx.source_tracker = SourceTracker()
        executor = make_executor(ctx)
        with patch(TRACKER_PATH, return_value=self.model.tracker):
            await executor.execute()
        assert isinstance(executor._compactor, RecordingCompactor)
        for event in executor._compactor.events:
            if isinstance(event, AgentStreamEvent) and event.type == AgentEventType.SOURCES.value:
                self.cards.extend((card["index"], card["url"]) for card in event.data)

    async def paused(self) -> bool:
        return bool((await self.agent.aget_state(THREAD_CONFIG)).interrupts)

    async def labels(self) -> list[tuple[int, str]]:
        """``(number, URL)`` of every source label the model read in the thread, in reading order."""
        messages: Sequence[BaseMessage] = (await self.agent.aget_state(THREAD_CONFIG)).values["messages"]
        return [
            (int(number), url)
            for message in messages
            if isinstance(message, ToolMessage)
            for number, url in re.findall(r"【(\d+)】 URL: (\S+)", str(message.content))
        ]


def _page(url: str) -> str:
    return url_dedup_key(strip_tracking_parameters(url), keep_fragment=True)


def _pages_by_number(pairs: Iterable[tuple[int, str]]) -> dict[int, set[str]]:
    pages: dict[int, set[str]] = {}
    for number, url in pairs:
        pages.setdefault(number, set()).add(_page(url))
    return pages


def _assert_every_number_names_one_page_and_its_card(
    labels: list[tuple[int, str]], cards: list[tuple[int, str]]
) -> None:
    read = _pages_by_number(labels)
    assert all(len(pages) == 1 for pages in read.values()), f"a number names two pages: {read}"
    assert _pages_by_number(cards) == read


TURNS_OF_TWO_SEARCHES: list[Step] = [("search", "first"), None, ("search", "second"), None]


@pytest.mark.asyncio
async def test_a_run_that_resumes_after_an_approval_pause_numbers_on_from_the_paused_run() -> None:
    thread = _Thread([("search", "first"), ("publish", "report"), ("search", "second"), None])

    with _provider_returns():
        await thread.run({"messages": [HumanMessage(content="question")]})
        assert await thread.paused()
        await thread.run(Command(resume="approved"))

    labels = await thread.labels()
    # P4 and P5 follow P3, and the page that is found again keeps the number it had.
    assert [(number, _page(url)) for number, url in labels] == [
        (1, _page(P1)),
        (2, _page(P2)),
        (3, _page(P3)),
        (4, _page(P4)),
        (2, _page(P2)),
        (5, _page(P5)),
    ]
    _assert_every_number_names_one_page_and_its_card(labels, thread.cards)


@pytest.mark.asyncio
async def test_the_next_turn_of_a_thread_numbers_on_from_the_earlier_turn() -> None:
    thread = _Thread(TURNS_OF_TWO_SEARCHES)

    with _provider_returns():
        await thread.run({"messages": [HumanMessage(content="turn one")]})
        await thread.run({"messages": [HumanMessage(content="turn two")]})

    labels = await thread.labels()
    assert [number for number, _ in labels] == [1, 2, 3, 4, 2, 5]
    _assert_every_number_names_one_page_and_its_card(labels, thread.cards)


@pytest.mark.asyncio
async def test_a_thread_that_cannot_be_read_still_runs_and_numbers_the_run_from_one(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class UnreadableByTheNumbering(InMemorySaver):
        """The graph reads its thread through ``aget_tuple``; only the numbering's own read (``aget``) fails."""

        async def aget(self, config: object) -> None:
            raise ConnectionError("checkpoint store is down")

    thread = _Thread(TURNS_OF_TWO_SEARCHES, UnreadableByTheNumbering())

    with _provider_returns(), caplog.at_level(logging.WARNING, logger=READ_ACCESS_LOGGER):
        await thread.run({"messages": [HumanMessage(content="turn one")]})
        await thread.run({"messages": [HumanMessage(content="turn two")]})

    assert [number for number, _ in await thread.labels()] == [1, 2, 3, 1, 2, 3]
    assert [record.getMessage() for record in caplog.records if record.name == READ_ACCESS_LOGGER] == [
        f"Failed to read checkpoint for thread {THREAD_ID}"
    ] * 2
