"""What a held-back answer leaves in the thread and where the instruction follows it."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.graph.message import add_messages

import myrm_agent_harness.agent.middlewares.completion.completion_guard.state as _cg_state
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
)
from tests.support.completion_guard_harness import (
    LOOP_GUARD_PATCH,
    make_state,
    pending,
)


class TestHoldBack:
    """A held-back draft stays, loses its finish-tool call, or leaves the conversation, and the instruction follows."""

    def setup_method(self) -> None:
        self.guard = CompletionGuard()
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_a_held_back_finish_tool_draft_leaves_the_conversation(self) -> None:
        """The draft's finish-tool call never runs, so it is removed instead of staying unanswered or as an empty
        assistant message; the instruction follows the message before it, and the draft object is left untouched."""
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "tc_answer",
                            "name": "request_answer_user_tool",
                            "args": {"reason": "Task complete"},
                        }
                    ],
                ),
            ]
        )
        user_message, original_ai = state["messages"]
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/a.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert pending(result).anchor_id == user_message.id
        assert [(type(m), m.id) for m in result["messages"]] == [(RemoveMessage, original_ai.id)]
        assert add_messages(state["messages"], result["messages"]) == [user_message]
        assert original_ai.tool_calls[0]["name"] == "request_answer_user_tool"

    @pytest.mark.asyncio
    async def test_a_finish_tool_draft_after_a_tool_round_leaves_the_instruction_behind_the_tool_result(self) -> None:
        """After a tool round the message before the draft is the tool result, so that is where the instruction goes:
        the request the model sees next ends with the tool result, not with an unanswered call."""
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc_write", "name": "file_write_tool", "args": {"path": "/tmp/a.py"}}],
                ),
                ToolMessage(content="written", tool_call_id="tc_write"),
                AIMessage(content="", tool_calls=[{"id": "tc_answer", "name": "request_answer_user_tool", "args": {}}]),
            ]
        )
        tool_result = state["messages"][2]
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/a.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert pending(result).anchor_id == tool_result.id
        assert add_messages(state["messages"], result["messages"])[-1].id == tool_result.id

    @pytest.mark.asyncio
    async def test_a_finish_tool_draft_that_says_something_keeps_its_words_and_loses_the_call(self) -> None:
        state = make_state(
            [
                HumanMessage(content="Change main.py and tell me when it is done."),
                AIMessage(
                    content="Both files are updated.",
                    tool_calls=[{"id": "tc_answer", "name": "request_answer_user_tool", "args": {}}],
                ),
            ]
        )
        original_ai = state["messages"][1]
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = [
                CallRecord(
                    tool_name="file_write_tool",
                    args_hash="abc",
                    args={"path": "/tmp/a.py"},
                    success_level=SuccessLevel.FULL_SUCCESS,
                )
            ]
            result = await self.guard.aafter_model(state, None)

        assert pending(result).anchor_id == original_ai.id
        (kept,) = add_messages(state["messages"], result["messages"])[1:]
        assert (kept.id, kept.content, kept.tool_calls) == (original_ai.id, "Both files are updated.", [])
        assert original_ai.tool_calls[0]["name"] == "request_answer_user_tool"

    @pytest.mark.asyncio
    async def test_a_held_back_text_draft_stays_and_the_instruction_follows_it(self) -> None:
        state = make_state(
            [
                HumanMessage(content="今天最新的 AI 新闻是什么？"),
                AIMessage(content="根据我所知，近期 AI 领域的主要进展包括多模态模型。"),
            ]
        )
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = []
            result = await self.guard.aafter_model(state, None)

        assert pending(result).anchor_id == state["messages"][1].id
        assert "messages" not in result

    @pytest.mark.asyncio
    async def test_an_answer_that_cannot_be_addressed_is_let_through(self) -> None:
        """A message without an id cannot anchor the instruction, so nothing is held back for it."""
        state = {
            "messages": [
                HumanMessage(content="今天最新的 AI 新闻是什么？"),
                AIMessage(content="根据我所知，近期 AI 领域的主要进展包括多模态模型。"),
            ]
        }
        with patch(LOOP_GUARD_PATCH) as mock_guard:
            mock_guard.return_value._window = []
            result = await self.guard.aafter_model(state, None)

        assert result is None
        assert _cg_state.current_run_state().pending_directive is None
