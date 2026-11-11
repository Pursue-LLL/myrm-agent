"""A held-back answer reaches the model as one request-only instruction, not as a made-up tool call.

The guard routes the run back to the model and leaves its instruction in the turn's guard state;
``CompletionDirectiveMiddleware`` writes it once behind the held-back draft, and every later request of the run
carries it at that place. The instruction is never stored in the conversation, so no approval, loop, trace or
analytics path ever sees it as a tool call. The delivery cases drive the middleware on its own; the chain case pins
where it sits; the real-agent cases run the whole agent under the default web chat security preset with only the
model scripted.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.runtime import Runtime

from myrm_agent_harness.agent._internals._agent_build import build_middlewares
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares.completion.completion_guard import reset_completion_guard
from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive_middleware import (
    CompletionDirectiveMiddleware,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.state import (
    PendingDirective,
    current_run_state,
)
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
from myrm_agent_harness.core.message_origin import runtime_human_message
from tests.support.completion_guard_harness import CHECK_MARK, CountingModel, registry_of, run_agent

_REQUEST = "今天最新的 AI 新闻是什么？"
_FROM_MEMORY = "根据我所知，近期 AI 领域的主要进展包括多模态模型与推理能力的提升。"
_DIRECTIVE = f"{CHECK_MARK}: say where the news came from."
_HONEST = "我这里没有联网检索工具，无法核实今天的最新新闻。以上内容来自训练数据，可能已过时。"
_TOOL_EVENTS = {"tool_start", "tool_approval_request"}
_FINISH_TOOL = "request_answer_user_tool"


class _ServerMiddleware(AgentMiddleware):
    """Stands for a middleware the server supplies."""


def _user() -> HumanMessage:
    return HumanMessage(content=_REQUEST, id="user-1")


def _draft() -> AIMessage:
    return AIMessage(content=_FROM_MEMORY, id="draft-1")


def _owe(anchor_id: str, text: str = _DIRECTIVE) -> None:
    current_run_state().pending_directive = PendingDirective(anchor_id=anchor_id, text=text)


async def _delivered(messages: list[BaseMessage], *, run: dict[str, object] | None = None) -> list[BaseMessage]:
    """The messages the model call receives when the middleware wraps a request holding ``messages``.

    Requests that share ``run`` belong to one run of the agent, so they share what the middleware wrote.
    """
    handler = AsyncMock(return_value=MagicMock())
    request = ModelRequest(
        model=MagicMock(), messages=messages, runtime=Runtime(context=run) if run is not None else None
    )
    await CompletionDirectiveMiddleware().awrap_model_call(request, handler)
    return list(handler.await_args.args[0].messages)


class TestDelivery:
    def setup_method(self) -> None:
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_the_instruction_follows_the_draft_it_was_written_for(self) -> None:
        draft = _draft()
        _owe(draft.id)

        sent = await _delivered([_user(), draft])

        assert [type(m) for m in sent] == [HumanMessage, AIMessage, HumanMessage]
        assert sent[1] is draft
        assert sent[2].content == _DIRECTIVE

    @pytest.mark.asyncio
    async def test_nothing_owed_changes_nothing(self) -> None:
        messages = [_user(), _draft()]

        assert await _delivered(messages) == messages

    @pytest.mark.asyncio
    async def test_the_instruction_is_not_written_once_the_conversation_moved_past_the_draft(self) -> None:
        draft = _draft()
        _owe(draft.id)
        with_tool_result = [_user(), draft, ToolMessage(content="ok", tool_call_id="t1", id="tool-1")]
        with_follow_up = [_user(), draft, HumanMessage(content="and tomorrow?", id="user-2")]

        assert await _delivered(with_tool_result) == with_tool_result
        assert await _delivered(with_follow_up) == with_follow_up

    @pytest.mark.asyncio
    async def test_a_notice_of_a_middleware_in_front_does_not_hide_the_draft(self) -> None:
        draft = _draft()
        _owe(draft.id)
        notice = runtime_human_message("[restore] files")

        sent = await _delivered([_user(), draft, notice])

        assert len(sent) == 4
        assert sent[1] is draft
        assert sent[2].content == _DIRECTIVE
        assert sent[3] is notice

    @pytest.mark.asyncio
    async def test_the_instruction_stays_behind_the_draft_on_every_later_request_of_the_run(self) -> None:
        run: dict[str, object] = {}
        draft = _draft()
        _owe(draft.id)
        first = await _delivered([_user(), draft], run=run)
        answer = AIMessage(content="a second answer", id="answer-2")

        later = await _delivered([_user(), draft, answer], run=run)

        assert later == [*first, answer]

    @pytest.mark.asyncio
    async def test_a_second_instruction_stands_behind_its_own_draft_and_the_first_stays(self) -> None:
        run: dict[str, object] = {}
        draft = _draft()
        _owe(draft.id)
        await _delivered([_user(), draft], run=run)
        second_draft = AIMessage(content=_FROM_MEMORY, id="draft-2")
        _owe(second_draft.id, "CRITICAL SYSTEM DIRECTIVE: answer now.")

        sent = await _delivered([_user(), draft, second_draft], run=run)

        assert [m.content for m in sent] == [
            _REQUEST,
            _FROM_MEMORY,
            _DIRECTIVE,
            _FROM_MEMORY,
            "CRITICAL SYSTEM DIRECTIVE: answer now.",
        ]

    @pytest.mark.asyncio
    async def test_the_instruction_of_one_run_is_not_carried_into_the_next(self) -> None:
        draft = _draft()
        _owe(draft.id)
        await _delivered([_user(), draft], run={})
        next_run = [_user(), draft, AIMessage(content="a second answer", id="answer-2")]

        assert await _delivered(next_run, run={}) == next_run

    @pytest.mark.asyncio
    async def test_an_instruction_for_another_draft_is_not_sent(self) -> None:
        _owe("draft-0")
        messages = [_user(), _draft()]

        assert await _delivered(messages) == messages

    @pytest.mark.asyncio
    async def test_delivery_leaves_the_conversation_the_run_keeps_untouched(self) -> None:
        draft = _draft()
        _owe(draft.id)
        messages = [_user(), draft]
        handler = AsyncMock(return_value=MagicMock())
        request = ModelRequest(model=MagicMock(), messages=messages)

        await CompletionDirectiveMiddleware().awrap_model_call(request, handler)

        assert len(messages) == 2
        assert len(request.messages) == 2
        assert len(handler.await_args.args[0].messages) == 3


class TestChain:
    def test_the_instruction_is_added_inside_every_middleware_the_server_supplies(self) -> None:
        """The server's own middlewares append to the last user message; they must see it before the instruction."""
        chain = build_middlewares(registry_of([]), [_ServerMiddleware()])

        def position(kind: type) -> int:
            return next(i for i, middleware in enumerate(chain) if isinstance(middleware, kind))

        assert position(CompletionDirectiveMiddleware) > position(_ServerMiddleware)


class TestRealAgent:
    """Whole agent under the default web chat preset; only the model is scripted."""

    def setup_method(self) -> None:
        reset_completion_guard()

    async def _run(self, tmp_path: Path) -> tuple[CountingModel, list[dict[str, object]]]:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)])
        events: list[dict[str, object]] = []
        await run_agent(
            tmp_path,
            build_channel_security_config("web_chat", None, local_mode=True),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.WORKSPACE_READ_ONLY,
            enable_shell_tools=True,
            events=events,
        )
        return model, events

    @pytest.mark.asyncio
    async def test_a_rejected_answer_asks_the_user_for_nothing_and_the_run_ends(self, tmp_path: Path) -> None:
        model, events = await self._run(tmp_path)

        kinds = {event["type"] for event in events}
        assert not kinds & _TOOL_EVENTS
        assert "message_end" in kinds
        assert 1 < len(model.requests) <= 5

    @pytest.mark.asyncio
    async def test_the_model_reads_the_instructions_only_after_the_draft_they_answer(self, tmp_path: Path) -> None:
        model, _ = await self._run(tmp_path)

        assert not any(CHECK_MARK in str(m.content) for m in model.transcripts[0])
        for transcript in model.transcripts[1:]:
            draft_at = next(i for i, m in enumerate(transcript) if isinstance(m, AIMessage))
            instructions = transcript[draft_at + 1 :]
            assert instructions
            assert all(isinstance(m, HumanMessage) for m in instructions)
            assert all(
                str(m.content).startswith(("CRITICAL COMPLETION CHECK", "CRITICAL SYSTEM DIRECTIVE"))
                for m in instructions
            )
            assert not any(str(m.content).startswith("CRITICAL") for m in transcript[:draft_at])

    @pytest.mark.asyncio
    async def test_every_request_of_the_run_extends_the_one_before_it(self, tmp_path: Path) -> None:
        """What the model was sent stays as it was, so a reply it signed to an earlier request still verifies."""
        model, _ = await self._run(tmp_path)

        assert len(model.transcripts) > 2
        for earlier, later in itertools.pairwise(model.transcripts):
            assert later[: len(earlier)] == earlier

    @pytest.mark.asyncio
    async def test_no_request_carries_a_tool_call_made_for_a_rejection(self, tmp_path: Path) -> None:
        model, _ = await self._run(tmp_path)

        for transcript in model.transcripts:
            assert not any(isinstance(m, AIMessage) and m.tool_calls for m in transcript)
            assert not any(isinstance(m, ToolMessage) for m in transcript)


class TestFinishToolDraft:
    """A draft that ends in the finish tool leaves the conversation: the model is asked again, so that call never runs.

    The whole agent runs with the run unable to look anything up, so the guard asks it once to say so; only the
    model is scripted, and it answers the first time with the finish tool and an empty message.
    """

    def setup_method(self) -> None:
        reset_completion_guard()

    @staticmethod
    def _model() -> CountingModel:
        draft = AIMessage(
            content="", tool_calls=[{"name": _FINISH_TOOL, "args": {}, "id": "call_finish", "type": "tool_call"}]
        )
        return CountingModel(responses=[draft, AIMessage(content=_HONEST)], answer_after_check=_HONEST)

    async def _run(
        self, tmp_path: Path, model: CountingModel, *, then: tuple[str, ...] = ()
    ) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        await run_agent(
            tmp_path,
            build_channel_security_config("web_chat", None, local_mode=True),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.WORKSPACE_READ_ONLY,
            enable_shell_tools=False,
            events=events,
            checkpointer=InMemorySaver(),
            then=then,
        )
        return events

    @pytest.mark.asyncio
    async def test_the_model_is_asked_again_with_the_instruction_after_the_users_message(self, tmp_path: Path) -> None:
        model = self._model()

        events = await self._run(tmp_path, model)

        first, asked_again = model.transcripts[:2]
        *conversation, instruction = asked_again
        assert [(type(m), m.id) for m in conversation] == [(type(m), m.id) for m in first]
        assert isinstance(instruction, HumanMessage)
        assert str(instruction.content).startswith(CHECK_MARK)
        assert "tool_approval_request" not in {e["type"] for e in events}

    @pytest.mark.asyncio
    async def test_no_request_of_the_turn_carries_an_empty_assistant_message(self, tmp_path: Path) -> None:
        model = self._model()

        await self._run(tmp_path, model)

        for transcript in model.transcripts:
            assert not any(isinstance(m, AIMessage) and not m.content for m in transcript)

    @pytest.mark.asyncio
    async def test_the_next_turn_of_the_chat_does_not_carry_the_draft(self, tmp_path: Path) -> None:
        model = self._model()

        await self._run(tmp_path, model, then=("谢谢，用一句话总结。",))

        next_turn = model.transcripts[2]
        assert [str(m.content) for m in next_turn if isinstance(m, AIMessage)] == [_HONEST]


class TestSupersededDraft:
    """The draft the guard held back is announced as superseded, so no consumer keeps it next to the answer."""

    def setup_method(self) -> None:
        reset_completion_guard()

    async def _run(
        self, tmp_path: Path, model: CountingModel, *, request: str = _REQUEST, can_look_up: bool = True
    ) -> list[dict[str, object]]:
        """A run that can look things up (a shell) is held to evidence; one that cannot is asked only to say so."""
        events: list[dict[str, object]] = []
        await run_agent(
            tmp_path,
            build_channel_security_config("web_chat", None, local_mode=True),
            model,
            request=request,
            file_access_mode=FileAccessMode.WORKSPACE_READ_ONLY,
            enable_shell_tools=can_look_up,
            events=events,
        )
        return events

    @pytest.mark.asyncio
    async def test_each_held_back_draft_is_announced_as_a_restart_of_the_answer(self, tmp_path: Path) -> None:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)])

        events = await self._run(tmp_path, model)

        restarts = [e for e in events if e["type"] == "status" and e.get("restart") is True]
        assert {e["step_key"] for e in restarts} == {"answer_recheck"}
        assert len(restarts) == len(model.requests) - 1

    @pytest.mark.asyncio
    async def test_the_answer_a_consumer_builds_is_the_one_that_replaced_the_draft(self, tmp_path: Path) -> None:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)], answer_after_check=_HONEST)

        events = await self._run(tmp_path, model, can_look_up=False)

        draft = AnswerDraft()
        for event in events:
            draft.feed(event)
        assert draft.text == _HONEST

    @pytest.mark.asyncio
    async def test_an_answer_that_passes_announces_nothing(self, tmp_path: Path) -> None:
        model = CountingModel(responses=[AIMessage(content=_FROM_MEMORY)])

        events = await self._run(tmp_path, model, request="解释一下什么是向量数据库")

        assert len(model.requests) == 1
        assert not [e for e in events if e.get("restart") is True]
