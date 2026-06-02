"""Tests for citation_rules_middleware — cache-safe HumanMessage injection."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
    CitationRulesMiddleware,
    _has_external_sources_in_current_turn,
    _is_final_answer_phase,
)


class TestIsFinalAnswerPhase:
    def test_detects_answer_tool(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="ok", tool_call_id="c1", name="request_answer_user_tool"),
        ]
        assert _is_final_answer_phase(messages) is True

    def test_rejects_other_tool(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="ok", tool_call_id="c1", name="web_search"),
        ]
        assert _is_final_answer_phase(messages) is False

    def test_empty_messages(self) -> None:
        assert _is_final_answer_phase([]) is False


class TestHasExternalSources:
    def test_detects_untrusted_marker(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA some_source\nresult",
                tool_call_id="c1",
                name="web_search",
            ),
        ]
        assert _has_external_sources_in_current_turn(messages) is True

    def test_no_marker(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(content="clean result", tool_call_id="c1", name="tool"),
        ]
        assert _has_external_sources_in_current_turn(messages) is False

    def test_no_human_message(self) -> None:
        messages = [
            ToolMessage(content="<<<UNTRUSTED_DATA x", tool_call_id="c1", name="tool"),
        ]
        assert _has_external_sources_in_current_turn(messages) is False


class TestCitationRulesMiddleware:
    @pytest.mark.asyncio
    async def test_injects_human_message_in_final_answer(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="user query"),
            AIMessage(content="searching"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search",
            ),
            AIMessage(content="answering"),
            ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        last_msg = called_request.messages[-1]
        assert isinstance(last_msg, HumanMessage)
        assert "[SYSTEM INSTRUCTION]" in str(last_msg.content)

    @pytest.mark.asyncio
    async def test_noop_when_not_final_answer(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        assert len(called_request.messages) == 2

    @pytest.mark.asyncio
    async def test_no_system_message_injected(self) -> None:
        """Citation injection must use HumanMessage, never SystemMessage."""
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA x\ndata",
                tool_call_id="c1",
                name="web_search",
            ),
            ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        system_msgs = [m for m in called_request.messages if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "sys"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["naked", "lean", "search"])
    async def test_skips_injection_in_naked_and_lean_mode(self, mode: str) -> None:
        """Citation rules must be skipped when prompt_mode is naked, lean, or search."""
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search",
            ),
            AIMessage(content="answering"),
            ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": mode}

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        assert len(called_request.messages) == 2
        assert not any("[SYSTEM INSTRUCTION]" in str(m.content) for m in called_request.messages)

    @pytest.mark.asyncio
    async def test_injects_in_full_mode(self) -> None:
        """Citation rules must still be injected in full mode."""
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search",
            ),
            AIMessage(content="answering"),
            ToolMessage(content="ok", tool_call_id="c2", name="request_answer_user_tool"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "full"}

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        last_msg = called_request.messages[-1]
        assert isinstance(last_msg, HumanMessage)
        assert "[SYSTEM INSTRUCTION]" in str(last_msg.content)
