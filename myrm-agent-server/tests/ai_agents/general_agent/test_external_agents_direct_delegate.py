"""The glue between the agent and the direct delegation stream: the pool, the cancel token and the session language."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin


def _mixin(pool: MagicMock, *, locale: str = "en") -> ExternalAgentsMixin:
    """The mixin holding ``pool``; a real agent also has the session ``locale``."""
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin._runtime_pool = pool
    mixin.locale = locale
    return mixin


@pytest.mark.asyncio
async def test_direct_delegate_stream_maps_runtime_events() -> None:
    from myrm_agent_harness.api import AgentEventType
    from myrm_agent_harness.toolkits.acp.types import RuntimeEventType

    mock_pool = MagicMock()
    mock_pool.get_config.return_value = SimpleNamespace(auth_mode="api_key")

    async def _fake_run_turn(*_args: object, **_kwargs: object):
        yield SimpleNamespace(type=RuntimeEventType.TEXT_DELTA, data={"content": "hello"})
        yield SimpleNamespace(
            type=RuntimeEventType.TOOL_START,
            data={"tool_name": "bash"},
        )
        yield SimpleNamespace(
            type=RuntimeEventType.TOOL_RESULT,
            data={"is_error": False},
        )
        yield SimpleNamespace(
            type=RuntimeEventType.USAGE_UPDATE,
            data={"input_tokens": 3, "output_tokens": 4},
        )

    mock_pool.run_turn = _fake_run_turn
    mock_pool.cancel = AsyncMock()
    mixin = _mixin(mock_pool)

    events: list[dict[str, object]] = []
    async for event in mixin._direct_delegate_stream("claude", "run task", chat_id="chat-1"):
        events.append(event)

    event_types = {str(event.get("type")) for event in events}
    assert AgentEventType.MESSAGE.value in event_types
    assert AgentEventType.TOKEN_USAGE.value in event_types
    assert AgentEventType.MESSAGE_END.value in event_types


@pytest.mark.asyncio
async def test_direct_delegate_stream_cancels_when_token_set() -> None:
    from myrm_agent_harness.api import AgentEventType
    from myrm_agent_harness.toolkits.acp.types import RuntimeEventType
    from myrm_agent_harness.utils import CancellationToken

    mock_pool = MagicMock()
    mock_pool.get_config.return_value = SimpleNamespace(auth_mode="subscription")
    cancel_token = CancellationToken()

    async def _fake_run_turn(*_args: object, **_kwargs: object):
        cancel_token.cancel()
        yield SimpleNamespace(type=RuntimeEventType.TEXT_DELTA, data={"content": "partial"})

    mock_pool.run_turn = _fake_run_turn
    mock_pool.cancel = AsyncMock()
    mixin = _mixin(mock_pool)

    events: list[dict[str, object]] = []
    async for event in mixin._direct_delegate_stream(
        "codex",
        "task",
        cancel_token=cancel_token,
        chat_id="chat-2",
    ):
        events.append(event)

    assert any(event.get("type") == AgentEventType.CANCELLED.value for event in events)
    mock_pool.cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_delegate_stream_words_a_failure_in_the_session_language() -> None:
    from myrm_agent_harness.api import AgentEventType
    from myrm_agent_harness.toolkits.acp.types import AcpError, AcpErrorCode, RuntimeEventType

    mock_pool = MagicMock()
    mock_pool.get_config.return_value = SimpleNamespace(auth_mode="subscription")

    async def _fake_run_turn(*_args: object, **_kwargs: object):
        yield SimpleNamespace(
            type=RuntimeEventType.ERROR,
            data={"error": AcpError(code=AcpErrorCode.AUTH_FAILED, message="Not logged in")},
        )

    mock_pool.run_turn = _fake_run_turn
    mock_pool.cancel = AsyncMock()

    events = [
        event async for event in _mixin(mock_pool, locale="zh-CN")._direct_delegate_stream("claude", "task", chat_id="chat-3")
    ]

    errors = [event for event in events if event["type"] == AgentEventType.ERROR.value]
    assert [error["diagnostic_result"]["locale"] for error in errors] == ["zh"]
    assert str(errors[0]["data"]).startswith("claude 尚未登录")
