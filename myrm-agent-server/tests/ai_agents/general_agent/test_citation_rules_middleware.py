"""Tests for citation_rules_middleware — cache-safe HumanMessage injection."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.ai_agents.general_agent.agent_middlewares.citation_rules_middleware import (
    _CITATION_RULES_TURN_KEY,
    CitationRulesMiddleware,
    _has_external_sources_in_current_turn,
    _should_inject_citation_rules,
)


class TestHasExternalSources:
    def test_detects_untrusted_marker(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA some_source\nresult",
                tool_call_id="c1",
                name="web_search_tool",
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


class TestShouldInjectCitationRules:
    def test_injects_when_untrusted_present(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
        ]
        should_inject, turn_idx = _should_inject_citation_rules(messages, {})
        assert should_inject is True
        assert turn_idx == 0

    def test_skips_when_already_injected_for_turn(self) -> None:
        messages = [
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
        ]
        ctx: dict[str, object] = {_CITATION_RULES_TURN_KEY: 0}
        should_inject, _ = _should_inject_citation_rules(messages, ctx)
        assert should_inject is False


class TestCitationRulesMiddleware:
    @pytest.mark.asyncio
    async def test_injects_when_untrusted_in_turn(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="user query"),
            AIMessage(content="searching"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
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
    async def test_injects_after_intermediate_tool_without_answer_tool(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
            AIMessage(content="running code"),
            ToolMessage(content="table output", tool_call_id="c2", name="bash_code_execute_tool"),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()
        ctx: dict[str, object] = {}

        mock_runtime = AsyncMock()
        mock_runtime.context = ctx

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

    @pytest.mark.asyncio
    async def test_noop_when_no_untrusted(self) -> None:
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
                name="web_search_tool",
            ),
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
    @pytest.mark.parametrize("mode", ["naked", "search"])
    async def test_skips_injection_in_naked_and_search_mode(self, mode: str) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
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
    async def test_injects_in_lean_mode(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "lean"}

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

    @pytest.mark.asyncio
    async def test_injects_in_full_mode(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
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

    @pytest.mark.asyncio
    async def test_injects_zh_rules_when_prompt_locale_zh(self) -> None:
        mw = CitationRulesMiddleware()

        state_messages: list[Any] = [
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "lean", "prompt_locale": "zh-CN"}

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
        assert "【" in str(last_msg.content)

    @pytest.mark.asyncio
    async def test_injects_only_once_per_turn(self) -> None:
        mw = CitationRulesMiddleware()
        ctx: dict[str, object] = {"prompt_mode": "full"}

        state_messages: list[Any] = [
            SystemMessage(content="system"),
            HumanMessage(content="query"),
            ToolMessage(
                content="<<<UNTRUSTED_DATA src\nresult",
                tool_call_id="c1",
                name="web_search_tool",
            ),
        ]

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = ctx

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="sys"), HumanMessage(content="q")],
            state={"messages": state_messages},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)
        first_count = len(mock_handler.call_args[0][0].messages)

        await mw.awrap_model_call(request, mock_handler)
        second_count = len(mock_handler.call_args[0][0].messages)

        assert first_count == 3
        assert second_count == 2
