"""A channel run that stops at a tool approval arms the approval timeout, unless the user already stopped it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.executor import ChannelAgentExecutor

_EXECUTOR = "app.core.channel_bridge.agent_executor.executor"
_APPROVAL_REQUEST: dict[str, object] = {
    "type": "tool_approval_request",
    "data": {
        "actionRequests": [{"action": "shell", "description": "run the build"}],
        "extensions": {"timeout": {"seconds": 120, "behavior": "deny"}},
    },
}


class _ApprovalAgent:
    """Stops at an approval request, then lingers the way a graph does while it winds down its interrupted run."""

    def __init__(self) -> None:
        self.winding_down = asyncio.Event()
        self._release = asyncio.Event()

    async def process_stream(self, **_kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        yield _APPROVAL_REQUEST
        self.winding_down.set()
        await self._release.wait()
        yield {"type": "message", "data": "unreachable"}

    def finish(self) -> None:
        self._release.set()


def _inbound(locale: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="Deploy it",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": locale},
    )


def _patched_executor(agent: _ApprovalAgent):
    prep = SimpleNamespace(
        agent=agent,
        token_ctx=None,
        chat_id="chat-db",
        chat_history=[],
        query_input="hi",
        channel_budget_key="",
        memory_settings=None,
        lite_model_cfg=None,
        session_was_auto_reset=False,
        session_policy=None,
        params=SimpleNamespace(agent_id="main"),
        agent_engine_params={},
        user_timezone="UTC",
    )
    return (
        patch(
            f"{_EXECUTOR}.prepare_channel_execution",
            AsyncMock(return_value=SimpleNamespace(pre_events=[], prep=prep)),
        ),
        patch("app.services.agent.runtime_context.build_agent_runtime_context", AsyncMock(return_value={})),
        patch(f"{_EXECUTOR}.finalize_channel_stream_reply", AsyncMock(return_value="reply")),
        patch(f"{_EXECUTOR}.finalize_agent_session", AsyncMock()),
    )


async def _drain(stream: AsyncGenerator[object, None]) -> None:
    async for _event in stream:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("locale", ["en", "zh-CN"])
async def test_a_run_that_stops_at_an_approval_arms_the_timeout_in_the_senders_locale(locale: str) -> None:
    agent = _ApprovalAgent()
    agent.finish()
    prepare, runtime_context, reply, finalize = _patched_executor(agent)

    with prepare, runtime_context, reply, finalize, patch(f"{_EXECUTOR}.schedule_channel_approval_timeout") as schedule:
        await _drain(ChannelAgentExecutor().execute_stream(_inbound(locale), cancel_token=CancellationToken()))

    schedule.assert_called_once()
    assert schedule.call_args.kwargs["locale"] == locale
    assert schedule.call_args.kwargs["peer"] == "chat-1"


@pytest.mark.asyncio
async def test_a_run_stopped_while_it_winds_down_after_an_approval_never_arms_the_timeout() -> None:
    """``/stop`` cancels the token, then the task; the run's cleanup must not re-arm what the stop just ended."""
    agent = _ApprovalAgent()
    token = CancellationToken()
    prepare, runtime_context, reply, finalize = _patched_executor(agent)

    with prepare, runtime_context, reply, finalize, patch(f"{_EXECUTOR}.schedule_channel_approval_timeout") as schedule:
        consumer = asyncio.create_task(_drain(ChannelAgentExecutor().execute_stream(_inbound("en"), cancel_token=token)))
        await asyncio.wait_for(agent.winding_down.wait(), timeout=2)

        token.cancel("User /stop command")
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consumer

    schedule.assert_not_called()
