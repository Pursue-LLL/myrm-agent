"""Tests for per-chat awaiting_approval session_status publishing in streaming.

Verifies that when an approval/clarification/tool_approval event is yielded
during agent streaming, the streaming finally-block publishes
'awaiting_approval' session_status via WorkspaceMultiplexer. A loop guard pause
travels as an approval_required event too, but nothing waits on an answer, so it
is neither filed as an approval nor announced as awaiting one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.streaming import ai_agent_service_stream


def _minimal_params(chat_id: str = "chat-attention-test") -> GeneralAgentParams:
    return GeneralAgentParams(
        query="hello",
        model_cfg=ModelConfig(
            model="gpt-4o-mini",
            api_key="test-key",
        ),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        chat_id=chat_id,
        message_id="msg-attention-test",
    )


@pytest.mark.asyncio
async def test_publishes_awaiting_approval_when_approval_event_yielded() -> None:
    """After stream with approval_required event, awaiting_approval status is published."""
    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    approval_event = {
        "type": "approval_required",
        "data": {
            "action_type": "shell_execute",
            "reason": "test",
            "severity": "warning",
        },
    }

    async def _fake_execute_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield approval_event

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "app.services.agent.streaming.get_agent_gateway",
        ) as mock_get_gateway,
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch(
            "app.services.agent.execution_cache.finalize_agent_session",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=MagicMock(id="approval-123"),
        ),
    ):
        mock_gateway = MagicMock()
        mock_gateway.execute_stream = _fake_execute_stream
        mock_get_gateway.return_value = mock_gateway

        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    assert len(events) >= 1
    mock_multiplexer.publish_session_status.assert_called_with("chat-attention-test", "awaiting_approval", "general")


@pytest.mark.asyncio
async def test_no_awaiting_approval_when_no_approval_event() -> None:
    """After stream without approval events, awaiting_approval is NOT published."""
    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    normal_event = {"type": "message", "data": "hello"}

    async def _fake_execute_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield normal_event

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "app.services.agent.streaming.get_agent_gateway",
        ) as mock_get_gateway,
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch(
            "app.services.agent.execution_cache.finalize_agent_session",
            new_callable=AsyncMock,
        ),
    ):
        mock_gateway = MagicMock()
        mock_gateway.execute_stream = _fake_execute_stream
        mock_get_gateway.return_value = mock_gateway

        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    assert len(events) >= 1
    mock_multiplexer.publish_session_status.assert_not_called()


@pytest.mark.asyncio
async def test_publishes_awaiting_approval_for_clarification_event() -> None:
    """clarification_required event also triggers awaiting_approval status."""
    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    clarification_event = {
        "type": "clarification_required",
        "data": {"question": "Which file?"},
    }

    async def _fake_execute_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield clarification_event

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "app.services.agent.streaming.get_agent_gateway",
        ) as mock_get_gateway,
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch(
            "app.services.agent.execution_cache.finalize_agent_session",
            new_callable=AsyncMock,
        ),
    ):
        mock_gateway = MagicMock()
        mock_gateway.execute_stream = _fake_execute_stream
        mock_get_gateway.return_value = mock_gateway

        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    assert len(events) >= 1
    mock_multiplexer.publish_session_status.assert_called_with("chat-attention-test", "awaiting_approval", "general")


@pytest.mark.asyncio
async def test_no_publish_when_chat_id_is_none() -> None:
    """If chat_id is None, awaiting_approval should NOT be published."""
    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer

    approval_event = {
        "type": "tool_approval_request",
        "data": {"tool": "bash", "args": {"cmd": "rm -rf /"}},
    }

    async def _fake_execute_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield approval_event

    params = _minimal_params()
    params.chat_id = None

    with (
        patch(
            "app.services.budget.enforcer.should_block_execution",
            new_callable=AsyncMock,
            return_value=False,
        ),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch(
            "app.services.agent.streaming.get_agent_gateway",
        ) as mock_get_gateway,
        patch(
            "app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer",
            mock_multiplexer_cls,
        ),
        patch(
            "app.services.agent.execution_cache.finalize_agent_session",
            new_callable=AsyncMock,
        ),
    ):
        mock_gateway = MagicMock()
        mock_gateway.execute_stream = _fake_execute_stream
        mock_get_gateway.return_value = mock_gateway

        events = [event async for event in ai_agent_service_stream(params)]

    assert len(events) >= 1
    mock_multiplexer.publish_session_status.assert_not_called()


@pytest.mark.asyncio
async def test_a_loop_guard_pause_is_not_filed_as_an_approval_nor_announced_as_awaiting_one() -> None:
    """The pause reaches the client untouched, but leaves no pending record that would turn the next message away."""
    mock_multiplexer = MagicMock()
    mock_multiplexer_cls = MagicMock()
    mock_multiplexer_cls.get.return_value = mock_multiplexer
    pause_event = {
        "type": "approval_required",
        "data": {"action_type": "tool_stuck", "tool_name": "bash_code_execute_tool", "tool_call_id": "call_3"},
    }

    async def _fake_execute_stream(*args, **kwargs):  # type: ignore[no-untyped-def]
        yield pause_event

    with (
        patch("app.services.budget.enforcer.should_block_execution", new_callable=AsyncMock, return_value=False),
        patch("app.services.budget.enforcer.reset_session_budget"),
        patch("app.services.agent.streaming.get_agent_gateway") as mock_get_gateway,
        patch("app.services.agent.streaming_support.multiplexer.WorkspaceMultiplexer", mock_multiplexer_cls),
        patch("app.services.agent.execution_cache.finalize_agent_session", new_callable=AsyncMock),
        patch(
            "app.services.approvals.registry.ApprovalRegistry.create_approval",
            new_callable=AsyncMock,
            return_value=MagicMock(id="approval-123"),
        ) as create_approval,
    ):
        mock_get_gateway.return_value = MagicMock(execute_stream=_fake_execute_stream)

        events = [event async for event in ai_agent_service_stream(_minimal_params())]

    pauses = [event for event in events if isinstance(event, dict) and event.get("type") == "approval_required"]
    assert len(pauses) == 1
    pause_data = pauses[0]["data"]
    assert isinstance(pause_data, dict)
    assert "approval_id" not in pause_data
    create_approval.assert_not_awaited()
    mock_multiplexer.publish_session_status.assert_not_called()
