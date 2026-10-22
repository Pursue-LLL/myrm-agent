"""The history rule across both layers: the real chat tables, the real SQLite checkpointer and a real LangGraph thread.

A turn here does what the server and the agent loop do for it: persist the user message, declare how it relates to
the thread, resolve that declaration against the thread, feed history only when it says so, run, store the answer
and record the completion. The graph answers with a counter, so an old answer can be told from a regenerated one.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from myrm_agent_harness.agent._internals.turn_history import TurnHistory, resolve_turn_history
from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer
from myrm_agent_harness.utils.chat_utils import convert_chat_history_simple

from app.services.agent.stream_session.chat_history_bootstrap import load_chat_history
from app.services.agent.stream_session.turn_history_sync import commit_turn_history_sync, resolve_turn_history_mode
from app.services.chat.chat_service import ChatService


class _ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


_Graph = CompiledStateGraph[_ChatState, None, _ChatState, _ChatState]


@pytest.fixture
async def saver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[BaseCheckpointSaver[str]]:
    checkpointer, cleanup = await create_checkpointer(mode="sqlite", sqlite_db_path=str(tmp_path / "checkpoints.db"))
    monkeypatch.setattr("app.platform_utils.get_checkpointer", lambda: checkpointer)
    try:
        yield checkpointer
    finally:
        await cleanup()


@pytest.fixture
def answers() -> Iterator[int]:
    return itertools.count(1)


@pytest.fixture
def graph(saver: BaseCheckpointSaver[str], answers: Iterator[int]) -> _Graph:
    async def answer(state: _ChatState) -> _ChatState:
        return {"messages": [AIMessage(content=f"{state['messages'][-1].content}#{next(answers)}")]}

    builder = StateGraph(_ChatState)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    return builder.compile(checkpointer=saver)


class _Conversation:
    def __init__(self, saver: BaseCheckpointSaver[str], graph: _Graph) -> None:
        self.chat_id = f"contract-{uuid.uuid4().hex[:10]}"
        self._saver = saver
        self._graph = graph
        self.modes: list[str] = []

    @property
    def _config(self) -> RunnableConfig:
        return {"configurable": {"thread_id": f"chat_{self.chat_id}", "checkpoint_ns": ""}}

    async def thread(self) -> list[object]:
        state = await self._graph.aget_state(self._config)
        return [message.content for message in state.values.get("messages", [])]

    async def send(self, text: str, *, outcome: str = "completed") -> TurnHistory:
        """One new-message turn; ``outcome`` is ``completed``, ``failed`` or ``waiting`` (on the user)."""
        user = await ChatService.ensure_chat_and_append_user_message(
            chat_id=self.chat_id,
            content=text,
            sent_at=datetime.now(tz=UTC),
            sent_timezone="UTC",
            message_id=str(uuid.uuid4()),
        )
        request = SimpleNamespace(chat_id=self.chat_id, resume_value=None, sibling_group_id=None, message_id=user.id)
        return await self._run(request, text, exclude_message_id=user.id, outcome=outcome)

    async def regenerate(self) -> TurnHistory:
        result = await ChatService.regenerate_last_turn(self.chat_id)
        request = SimpleNamespace(
            chat_id=self.chat_id,
            resume_value=None,
            sibling_group_id=result.sibling_group_id,
            message_id=str(uuid.uuid4()),
        )
        return await self._run(request, result.query, exclude_message_id=None, outcome="completed")

    async def _run(
        self,
        request: SimpleNamespace,
        text: str,
        *,
        exclude_message_id: str | None,
        outcome: str,
    ) -> TurnHistory:
        history = await load_chat_history(request, exclude_message_id=exclude_message_id)
        mode = await resolve_turn_history_mode(request, exclude_message_id=exclude_message_id)
        turn = await resolve_turn_history(self._saver, f"chat_{self.chat_id}", mode)
        fed = convert_chat_history_simple(history) if turn.feeds_history else []
        await self._graph.ainvoke({"messages": [*fed, HumanMessage(content=text)]}, self._config)
        self.modes.append(turn.mode)
        if outcome != "failed":
            await self.store_answer(request, text)
        await commit_turn_history_sync(
            self.finished(request, turn.telemetry()["history_mode"], failed=outcome == "failed"),
            pending_hitl=outcome == "waiting",
        )
        return turn

    async def store_answer(self, request: SimpleNamespace, text: str) -> None:
        state = await self._graph.aget_state(self._config)
        await ChatService.persist_assistant_message_safe(
            self.chat_id,
            str(state.values["messages"][-1].content),
            sibling_group_id=request.sibling_group_id,
            request_message_id=request.message_id,
        )

    def finished(self, request: SimpleNamespace, history_mode: object, *, failed: bool = False) -> SimpleNamespace:
        return SimpleNamespace(
            request=request,
            cancel_token=SimpleNamespace(is_cancelled=False),
            had_fatal_error=failed,
            collector=SimpleNamespace(extra_data={"tokenEconomics": {"turn_context": {"history_mode": history_mode}}}),
        )


@pytest.fixture
def conversation(saver: BaseCheckpointSaver[str], graph: _Graph) -> _Conversation:
    return _Conversation(saver, graph)


@pytest.mark.asyncio
async def test_the_thread_grows_by_the_new_exchange_only(conversation: _Conversation) -> None:
    for text in ("a", "b", "c"):
        await conversation.send(text)

    assert conversation.modes == ["replace", "continue", "continue"]
    assert await conversation.thread() == ["a", "a#1", "b", "b#2", "c", "c#3"]


@pytest.mark.asyncio
async def test_an_undone_turn_leaves_nothing_of_itself_on_the_thread(conversation: _Conversation) -> None:
    await conversation.send("a")
    await conversation.send("b")

    await ChatService.undo_last_turn(conversation.chat_id)
    await conversation.send("c")

    assert conversation.modes == ["replace", "continue", "replace"]
    assert await conversation.thread() == ["a", "a#1", "c", "c#3"]


@pytest.mark.asyncio
async def test_a_regenerate_keeps_one_copy_of_its_query_and_drops_the_replaced_answer(
    conversation: _Conversation,
) -> None:
    await conversation.send("a")
    await conversation.send("b")

    await conversation.regenerate()

    assert conversation.modes == ["replace", "continue", "replace"]
    assert await conversation.thread() == ["a", "a#1", "b", "b#3"]


@pytest.mark.asyncio
async def test_the_query_a_regenerate_re_sends_is_not_part_of_its_history(
    conversation: _Conversation,
) -> None:
    await conversation.send("a")
    result = await ChatService.regenerate_last_turn(conversation.chat_id)
    request = SimpleNamespace(chat_id=conversation.chat_id, sibling_group_id=result.sibling_group_id)

    loaded = await ChatService.load_web_chat_history(conversation.chat_id)
    history = await load_chat_history(request, exclude_message_id=None)

    assert [entry[0] for entry in loaded] == ["human"]
    assert history == []


@pytest.mark.asyncio
async def test_a_failed_turn_is_rebuilt_from_what_was_stored(conversation: _Conversation) -> None:
    await conversation.send("a")
    await conversation.send("b", outcome="failed")
    await conversation.send("c")

    assert conversation.modes == ["replace", "continue", "replace"]
    assert await conversation.thread() == ["a", "a#1", "b", "c", "c#3"]


@pytest.mark.asyncio
async def test_a_turn_waiting_on_the_user_is_rebuilt_by_the_next_message(conversation: _Conversation) -> None:
    await conversation.send("a")
    await conversation.send("b", outcome="waiting")
    await conversation.send("c")

    assert conversation.modes == ["replace", "continue", "replace"]
    assert await conversation.thread() == ["a", "a#1", "b", "b#2", "c", "c#3"]


@pytest.mark.asyncio
async def test_a_resumed_turn_is_recorded_so_the_next_message_continues(conversation: _Conversation) -> None:
    await conversation.send("a")
    await conversation.send("b", outcome="waiting")
    resumed = SimpleNamespace(chat_id=conversation.chat_id, message_id=str(uuid.uuid4()), sibling_group_id=None)
    await conversation.store_answer(resumed, "b")
    await commit_turn_history_sync(conversation.finished(resumed, "resume"), pending_hitl=False)

    await conversation.send("c")

    assert conversation.modes[-1] == "continue"


@pytest.mark.asyncio
async def test_a_notice_the_server_appended_reaches_the_model_through_a_rebuild(conversation: _Conversation) -> None:
    await conversation.send("a")
    await ChatService.persist_assistant_message_safe(
        conversation.chat_id,
        "background job finished",
        extra_data={"background_job": True},
    )

    await conversation.send("b")

    assert conversation.modes == ["replace", "replace"]
    assert await conversation.thread() == ["a", "a#1", "background job finished", "b", "b#2"]
