"""Tests for restore_source_numbering: a run seeds its tracker with the numbers its thread already stated.

The thread is stored the way a run stores it: a compiled graph writes its messages to a checkpointer, and the tool
messages carry the sources the interceptor stamped. The tracker then answers with the stored numbers.

Covers:
- the numbers of earlier tool calls are kept and new pages continue after the highest one
- threads and messages with nothing stamped leave the numbering to start from one
- no checkpointer, no thread id, an unreadable thread: the run goes on, numbering from one
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages

from myrm_agent_harness.agent.middlewares.tooling.tool_sources_hoisting import TOOL_SOURCES_KWARG
from myrm_agent_harness.agent.streaming.source_numbering import restore_source_numbering
from myrm_agent_harness.agent.streaming.source_tracker import SourceTracker

THREAD_ID = "thread-1"
READ_ACCESS_LOGGER = "myrm_agent_harness.runtime.checkpointing.read_access"


def _config(thread_id: str | None = THREAD_ID) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}} if thread_id is not None else {}


def _tool_message(call_id: str, sources: object) -> ToolMessage:
    return ToolMessage(
        content="result", name="web_search", tool_call_id=call_id, additional_kwargs={TOOL_SOURCES_KWARG: sources}
    )


class _State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


async def _saver_holding(messages: list[AnyMessage]) -> InMemorySaver:
    """A checkpointer whose thread holds ``messages``, written by a graph the way a run writes them."""

    def write_thread(state: _State) -> _State:
        return {"messages": [*state["messages"], *messages]}

    saver = InMemorySaver()
    graph = StateGraph(_State)
    graph.add_node("write_thread", write_thread)
    graph.add_edge(START, "write_thread")
    await graph.compile(checkpointer=saver).ainvoke({"messages": []}, _config())
    return saver


def _stated(*pages: tuple[str, int]) -> list[dict[str, object]]:
    return [{"url": url, "index": number, "title": url} for url, number in pages]


async def _restored(messages: list[AnyMessage], config: RunnableConfig | None = None) -> SourceTracker:
    tracker = SourceTracker()
    await restore_source_numbering(tracker, await _saver_holding(messages), config if config is not None else _config())
    return tracker


class TestTheThreadsStoredNumbers:
    @pytest.mark.asyncio
    async def test_the_numbers_of_every_stored_tool_call_are_kept(self) -> None:
        tracker = await _restored(
            [
                HumanMessage(content="question"),
                AIMessage(content="", tool_calls=[{"name": "web_search", "args": {}, "id": "c1"}]),
                _tool_message("c1", _stated(("https://a.test", 3), ("https://b.test", 1))),
                AIMessage(content="", tool_calls=[{"name": "web_fetch", "args": {}, "id": "c2"}]),
                _tool_message("c2", _stated(("https://c.test", 2))),
            ]
        )

        assert [tracker.index_for({"url": url}) for url in ("https://a.test", "https://b.test", "https://c.test")] == [
            3,
            1,
            2,
        ]

    @pytest.mark.asyncio
    async def test_a_page_the_thread_never_numbered_continues_after_the_highest_number(self) -> None:
        tracker = await _restored([_tool_message("c1", _stated(("https://a.test", 2), ("https://b.test", 5)))])

        assert tracker.index_for({"url": "https://new.test"}) == 6

    @pytest.mark.asyncio
    async def test_a_page_read_in_a_later_message_under_a_new_spelling_keeps_its_number(self) -> None:
        tracker = await _restored([_tool_message("c1", _stated(("https://www.a.test/x/", 4)))])

        assert tracker.index_for({"url": "https://A.test/x"}) == 4


class TestMessagesWithNothingToRestore:
    @pytest.mark.asyncio
    async def test_a_tool_message_without_hoisted_sources_changes_nothing(self) -> None:
        plain = ToolMessage(content="result", name="bash", tool_call_id="c1")

        tracker = await _restored([HumanMessage(content="hi"), plain])

        assert tracker.index_for({"url": "https://a.test"}) == 1

    @pytest.mark.asyncio
    async def test_sources_a_thread_stored_before_numbers_were_stamped_leave_numbering_to_start_from_one(self) -> None:
        tracker = await _restored([_tool_message("c1", [{"url": "https://a.test", "title": "A"}])])

        assert tracker.index_for({"url": "https://b.test"}) == 1

    @pytest.mark.asyncio
    async def test_only_tool_messages_are_read(self) -> None:
        ai = AIMessage(content="reply", additional_kwargs={TOOL_SOURCES_KWARG: _stated(("https://a.test", 9))})

        tracker = await _restored([ai])

        assert tracker.index_for({"url": "https://a.test"}) == 1

    @pytest.mark.asyncio
    async def test_a_hoisted_value_that_is_not_a_list_of_source_dicts_is_ignored(self) -> None:
        tracker = await _restored(
            [
                _tool_message("c1", "https://a.test"),
                _tool_message("c2", ["https://b.test", _stated(("https://c.test", 3))[0]]),
            ]
        )

        assert tracker.index_for({"url": "https://c.test"}) == 3
        assert tracker.index_for({"url": "https://b.test"}) == 4


class TestRunsThatCannotRestore:
    @pytest.mark.asyncio
    async def test_a_thread_without_a_checkpoint_yet_changes_nothing(self) -> None:
        tracker = SourceTracker()

        await restore_source_numbering(tracker, InMemorySaver(), _config("a-new-thread"))

        assert tracker.index_for({"url": "https://a.test"}) == 1

    @pytest.mark.asyncio
    async def test_a_run_without_a_checkpointer_numbers_from_one_without_a_sound(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        tracker = SourceTracker()

        with caplog.at_level(logging.DEBUG):
            await restore_source_numbering(tracker, None, _config())

        assert tracker.index_for({"url": "https://a.test"}) == 1
        assert caplog.records == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("config", [{}, {"configurable": {}}, {"configurable": {"thread_id": 7}}])
    async def test_a_run_without_a_thread_id_is_not_looked_up(self, config: RunnableConfig) -> None:
        reads: list[Mapping[str, object]] = []

        class Recording:
            async def aget(self, read_config: Mapping[str, object]) -> None:
                reads.append(read_config)

        tracker = SourceTracker()

        await restore_source_numbering(tracker, Recording(), config)

        assert reads == []
        assert tracker.index_for({"url": "https://a.test"}) == 1

    @pytest.mark.asyncio
    async def test_an_unreadable_thread_numbers_from_one_and_the_failure_is_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class Unreachable:
            async def aget(self, _config: Mapping[str, object]) -> None:
                raise ConnectionError("checkpoint store is down")

        tracker = SourceTracker()

        with caplog.at_level(logging.WARNING, logger=READ_ACCESS_LOGGER):
            await restore_source_numbering(tracker, Unreachable(), _config())

        assert tracker.index_for({"url": "https://a.test"}) == 1
        assert [record.getMessage() for record in caplog.records] == [
            f"Failed to read checkpoint for thread {THREAD_ID}"
        ]
