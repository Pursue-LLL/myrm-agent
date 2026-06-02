"""Tests for widget_capability_middleware — conditional widget declaration injection."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai_agents.agent_middlewares.widget_capability_middleware import (
    WIDGET_CAPABILITY_MARKER,
    WIDGET_CAPABILITY_PROMPT,
    WidgetCapabilityMiddleware,
    _find_insert_idx,
    _has_widget_capability_injected,
)


class TestHasWidgetCapabilityInjected:
    def test_detects_existing_widget_marker(self) -> None:
        messages: list[Any] = [
            SystemMessage(content=f"prefix {WIDGET_CAPABILITY_MARKER} rest"),
        ]
        assert _has_widget_capability_injected(messages) is True

    def test_no_marker(self) -> None:
        messages: list[Any] = [
            SystemMessage(content="clean system message"),
        ]
        assert _has_widget_capability_injected(messages) is False

    def test_empty_messages(self) -> None:
        assert _has_widget_capability_injected([]) is False

    def test_only_scans_first_6(self) -> None:
        messages: list[Any] = [SystemMessage(content="clean")] * 7
        messages[6] = SystemMessage(content=f"has {WIDGET_CAPABILITY_MARKER}")
        assert _has_widget_capability_injected(messages) is False


class TestFindInsertIdx:
    def test_after_system_messages(self) -> None:
        messages: list[Any] = [
            SystemMessage(content="sys1"),
            SystemMessage(content="sys2"),
            HumanMessage(content="user"),
        ]
        assert _find_insert_idx(messages) == 2

    def test_no_system_message(self) -> None:
        messages: list[Any] = [HumanMessage(content="user")]
        assert _find_insert_idx(messages) == 0

    def test_all_system_messages(self) -> None:
        messages: list[Any] = [
            SystemMessage(content="s1"),
            SystemMessage(content="s2"),
            SystemMessage(content="s3"),
        ]
        assert _find_insert_idx(messages) == 3


class TestWidgetCapabilityMiddleware:
    @pytest.mark.asyncio
    async def test_injects_on_first_call(self) -> None:
        mw = WidgetCapabilityMiddleware()

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="core prompt"), HumanMessage(content="q")],
            state={"messages": [SystemMessage(content="core prompt"), HumanMessage(content="q")]},
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        contents = [m.content for m in called_request.messages if isinstance(m, SystemMessage)]
        assert any(WIDGET_CAPABILITY_MARKER in c for c in contents)

    @pytest.mark.asyncio
    async def test_skips_if_already_injected(self) -> None:
        mw = WidgetCapabilityMiddleware()

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        request = ModelRequest(
            model=AsyncMock(),
            messages=[
                SystemMessage(content="core prompt"),
                SystemMessage(content=WIDGET_CAPABILITY_PROMPT),
                HumanMessage(content="q"),
            ],
            state={"messages": [
                SystemMessage(content="core prompt"),
                SystemMessage(content=WIDGET_CAPABILITY_PROMPT),
                HumanMessage(content="q"),
            ]},
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        assert len(called_request.messages) == 3

    @pytest.mark.asyncio
    async def test_skips_in_naked_mode(self) -> None:
        """Widget capability must be skipped in naked mode."""
        mw = WidgetCapabilityMiddleware()

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "naked"}

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="core"), HumanMessage(content="q")],
            state={"messages": [SystemMessage(content="core"), HumanMessage(content="q")]},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        assert len(called_request.messages) == 2
        contents = [m.content for m in called_request.messages if isinstance(m, SystemMessage)]
        assert not any(WIDGET_CAPABILITY_MARKER in c for c in contents)

    @pytest.mark.asyncio
    async def test_injects_in_lean_mode(self) -> None:
        """Widget capability should still inject in lean mode (only naked skips)."""
        mw = WidgetCapabilityMiddleware()

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "lean"}

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="core"), HumanMessage(content="q")],
            state={"messages": [SystemMessage(content="core"), HumanMessage(content="q")]},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        contents = [m.content for m in called_request.messages if isinstance(m, SystemMessage)]
        assert any(WIDGET_CAPABILITY_MARKER in c for c in contents)

    @pytest.mark.asyncio
    async def test_injects_in_full_mode(self) -> None:
        """Widget capability should inject in full mode."""
        mw = WidgetCapabilityMiddleware()

        mock_handler = AsyncMock()
        mock_handler.return_value = AsyncMock()

        mock_runtime = AsyncMock()
        mock_runtime.context = {"prompt_mode": "full"}

        request = ModelRequest(
            model=AsyncMock(),
            messages=[SystemMessage(content="core"), HumanMessage(content="q")],
            state={"messages": [SystemMessage(content="core"), HumanMessage(content="q")]},
            runtime=mock_runtime,
        )

        await mw.awrap_model_call(request, mock_handler)

        called_request = mock_handler.call_args[0][0]
        contents = [m.content for m in called_request.messages if isinstance(m, SystemMessage)]
        assert any(WIDGET_CAPABILITY_MARKER in c for c in contents)
