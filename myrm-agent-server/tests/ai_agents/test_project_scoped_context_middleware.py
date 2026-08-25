import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware import ModelRequest, ModelResponse

from app.ai_agents.agent_middlewares.project_scoped_context_middleware import (
    project_scoped_workspace_middleware,
    _has_scoped_workspace_injected,
    _build_scoped_workspace_snippet,
)


def test_build_scoped_workspace_snippet():
    snippet = _build_scoped_workspace_snippet("my-service/backend")
    assert '<project_scoped_workspace path="my-service/backend">' in snippet
    assert "ast_symbol_search_tool" in snippet
    assert "</project_scoped_workspace>" in snippet


@pytest.mark.asyncio
async def test_project_scoped_workspace_middleware_injects():
    mock_handler = AsyncMock()
    mock_handler.return_value = MagicMock(spec=ModelResponse)

    req = MagicMock(spec=ModelRequest)
    req.context = {"active_project_root": "frontend/src"}
    req.messages = [
        SystemMessage(content="You are a helpful assistant."),
        HumanMessage(content="Explain the auth flow."),
    ]

    def override_fn(messages=None):
        m = MagicMock(spec=ModelRequest)
        m.messages = messages
        return m

    req.override = override_fn

    await project_scoped_workspace_middleware.awrap_model_call(req, mock_handler)
    assert mock_handler.called

    called_req = mock_handler.call_args[0][0]
    injected_messages = called_req.messages
    assert len(injected_messages) == 3
    assert isinstance(injected_messages[1], SystemMessage)
    assert '<project_scoped_workspace path="frontend/src">' in injected_messages[1].content


@pytest.mark.asyncio
async def test_project_scoped_workspace_middleware_idempotent():
    mock_handler = AsyncMock()
    mock_handler.return_value = MagicMock(spec=ModelResponse)

    req = MagicMock(spec=ModelRequest)
    req.context = {"active_project_root": "frontend/src"}
    req.messages = [
        SystemMessage(content="You are a helpful assistant."),
        SystemMessage(content='<project_scoped_workspace path="frontend/src">...</project_scoped_workspace>'),
        HumanMessage(content="Hello"),
    ]

    await project_scoped_workspace_middleware.awrap_model_call(req, mock_handler)
    assert mock_handler.called
    called_req = mock_handler.call_args[0][0]
    # No override called, original messages kept
    assert called_req == req
