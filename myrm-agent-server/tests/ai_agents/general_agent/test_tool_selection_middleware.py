"""Tests for tool_selection_middleware — L2 convergence protection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware import (
    ToolSelectionMiddleware,
    _count_trailing_answer_tool_messages,
    reset_answer_tool_convergence,
)


class TestCountTrailingAnswerToolMessages:
    def test_empty_list(self) -> None:
        assert _count_trailing_answer_tool_messages([]) == 0

    def test_no_answer_tool(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="ok", tool_call_id="c1", name="web_search"),
        ]
        assert _count_trailing_answer_tool_messages(messages) == 0

    def test_single_trailing_answer(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
        ]
        assert _count_trailing_answer_tool_messages(messages) == 1

    def test_multiple_trailing_answers(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
            ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool"),
            ToolMessage(content="ok", tool_call_id="c3", name="request_answer_user_tool"),
        ]
        assert _count_trailing_answer_tool_messages(messages) == 3

    def test_non_consecutive_at_tail(self) -> None:
        messages = [
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
            ToolMessage(content="ok", tool_call_id="c2", name="web_search"),
            ToolMessage(content="ok", tool_call_id="c3", name="request_answer_user_tool"),
        ]
        assert _count_trailing_answer_tool_messages(messages) == 1

    def test_answer_in_middle_only(self) -> None:
        messages = [
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
            AIMessage(content="response"),
        ]
        assert _count_trailing_answer_tool_messages(messages) == 0


class TestResetAnswerToolConvergence:
    def test_resets_to_zero(self) -> None:
        from app.ai_agents.general_agent.agent_middlewares.tool_selection_middleware import (
            _answer_consecutive_count,
        )
        _answer_consecutive_count.set(5)
        reset_answer_tool_convergence()
        assert _answer_consecutive_count.get() == 0


def _make_request(messages: list[object], tool_choice: str = "auto") -> ModelRequest:
    """Create a ModelRequest with given messages in state."""
    return ModelRequest(
        model=AsyncMock(),
        messages=[],
        tools=[],
        tool_choice=tool_choice,
        state={"messages": messages},
    )


@pytest.fixture(autouse=True)
def _reset_convergence() -> None:
    """Reset convergence state before each test."""
    reset_answer_tool_convergence()


class TestToolSelectionMiddlewareConvergence:
    """Test the L2 convergence mechanism."""

    @pytest.mark.asyncio
    async def test_first_answer_sets_none(self) -> None:
        """First request_answer_user_tool call should set tool_choice='none'."""
        mw = ToolSelectionMiddleware()
        handler = AsyncMock(return_value="response")

        messages = [
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
        ]
        request = _make_request(messages)
        await mw.awrap_model_call(request, handler)

        called_request = handler.call_args[0][0]
        assert called_request.tool_choice == "none"

    @pytest.mark.asyncio
    async def test_second_answer_still_none(self) -> None:
        """Second consecutive call should still set tool_choice='none'."""
        mw = ToolSelectionMiddleware()
        handler = AsyncMock(return_value="response")

        msg = ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool")
        await mw.awrap_model_call(_make_request([msg]), handler)

        handler.reset_mock()
        msg2 = ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool")
        await mw.awrap_model_call(_make_request([msg2]), handler)

        called_request = handler.call_args[0][0]
        assert called_request.tool_choice == "none"

    @pytest.mark.asyncio
    async def test_third_answer_triggers_convergence(self) -> None:
        """Third consecutive call should restore tool_choice to original (convergence)."""
        mw = ToolSelectionMiddleware()
        handler = AsyncMock(return_value="response")

        for i in range(3):
            handler.reset_mock()
            msg = ToolMessage(content="ok", tool_call_id=f"c{i}", name="request_answer_user_tool")
            await mw.awrap_model_call(_make_request([msg]), handler)

        called_request = handler.call_args[0][0]
        assert called_request.tool_choice != "none"

    @pytest.mark.asyncio
    async def test_non_answer_tool_resets_counter(self) -> None:
        """A non-answer tool call should reset the consecutive counter."""
        mw = ToolSelectionMiddleware()
        handler = AsyncMock(return_value="response")

        msg1 = ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool")
        await mw.awrap_model_call(_make_request([msg1]), handler)

        other = ToolMessage(content="ok", tool_call_id="c2", name="web_search")
        await mw.awrap_model_call(_make_request([other]), handler)

        handler.reset_mock()
        msg3 = ToolMessage(content="ok", tool_call_id="c3", name="request_answer_user_tool")
        await mw.awrap_model_call(_make_request([msg3]), handler)

        called_request = handler.call_args[0][0]
        assert called_request.tool_choice == "none"

    @pytest.mark.asyncio
    async def test_no_tool_messages_passthrough(self) -> None:
        """Request without tool messages should pass through without modification."""
        mw = ToolSelectionMiddleware()
        handler = AsyncMock(return_value="response")

        request = _make_request([HumanMessage(content="hello")])
        await mw.awrap_model_call(request, handler)

        called_request = handler.call_args[0][0]
        assert called_request.tool_choice == "auto"
