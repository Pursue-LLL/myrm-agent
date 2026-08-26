"""Tests for project_scoped_context_middleware — cache-safe project boundary and AST search injection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai_agents.agent_middlewares.project_scoped_context_middleware import (
    PROJECT_SCOPED_WORKSPACE_MARKER,
    ProjectScopedWorkspaceMiddleware,
    _find_insert_idx,
    _has_scoped_workspace_injected,
)


class TestHasScopedWorkspaceInjected:
    def test_detects_existing_marker(self) -> None:
        messages = [
            SystemMessage(content=f"prefix {PROJECT_SCOPED_WORKSPACE_MARKER} path='/workspace/src'> rest"),
        ]
        assert _has_scoped_workspace_injected(messages) is True

    def test_no_marker(self) -> None:
        messages = [
            SystemMessage(content="clean system message"),
        ]
        assert _has_scoped_workspace_injected(messages) is False

    def test_empty_messages(self) -> None:
        assert _has_scoped_workspace_injected([]) is False


class TestFindInsertIdx:
    def test_after_system_messages(self) -> None:
        messages = [
            SystemMessage(content="sys1"),
            SystemMessage(content="sys2"),
            HumanMessage(content="user query"),
        ]
        assert _find_insert_idx(messages) == 2

    def test_all_system_messages(self) -> None:
        messages = [
            SystemMessage(content="sys1"),
            SystemMessage(content="sys2"),
        ]
        assert _find_insert_idx(messages) == 2

    def test_no_system_messages(self) -> None:
        messages = [
            HumanMessage(content="user query"),
        ]
        assert _find_insert_idx(messages) == 0


class TestProjectScopedWorkspaceMiddleware:
    @pytest.mark.asyncio
    async def test_injects_scoped_workspace_when_project_dir_present(self) -> None:
        middleware = ProjectScopedWorkspaceMiddleware()
        mock_handler = AsyncMock()
        mock_handler.return_value = "response"

        req = ModelRequest(
            messages=[
                SystemMessage(content="system prompt"),
                HumanMessage(content="how does auth work?"),
            ],
            model=None,
            state={"configurable": {"project_dir": "services/auth"}},
        )

        res = await middleware.awrap_model_call(req, mock_handler)
        assert res == "response"

        called_req = mock_handler.call_args[0][0]
        assert len(called_req.messages) == 3
        injected = called_req.messages[1]
        assert isinstance(injected, SystemMessage)
        assert PROJECT_SCOPED_WORKSPACE_MARKER in injected.content
        assert "services/auth" in injected.content
        assert "ast_symbol_search_tool" in injected.content

    @pytest.mark.asyncio
    async def test_no_injection_when_no_project_dir(self) -> None:
        middleware = ProjectScopedWorkspaceMiddleware()
        mock_handler = AsyncMock()
        mock_handler.return_value = "response"

        req = ModelRequest(
            messages=[
                SystemMessage(content="system prompt"),
                HumanMessage(content="hello"),
            ],
            model=None,
            state={"configurable": {}},
        )

        res = await middleware.awrap_model_call(req, mock_handler)
        assert res == "response"

        called_req = mock_handler.call_args[0][0]
        assert len(called_req.messages) == 2
        assert PROJECT_SCOPED_WORKSPACE_MARKER not in called_req.messages[0].content

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate_injection(self) -> None:
        middleware = ProjectScopedWorkspaceMiddleware()
        mock_handler = AsyncMock()
        mock_handler.return_value = "response"

        req = ModelRequest(
            messages=[
                SystemMessage(content="system prompt"),
                SystemMessage(content=f"{PROJECT_SCOPED_WORKSPACE_MARKER} path='services/auth'>..."),
                HumanMessage(content="next turn query"),
            ],
            model=None,
            state={"configurable": {"project_dir": "services/auth"}},
        )

        res = await middleware.awrap_model_call(req, mock_handler)
        assert res == "response"

        called_req = mock_handler.call_args[0][0]
        assert len(called_req.messages) == 3
