"""Tests for auto busy_input_mode dispatch in AgentRouter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.routing.router import AgentRouter
from app.channels.routing.router_keys import routing_session_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage


def _make_bus() -> MagicMock:
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


def _make_router(**overrides: object) -> AgentRouter:
    bus = overrides.pop("bus", _make_bus())
    pairing = overrides.pop("pairing", MagicMock())
    executor = overrides.pop("executor", MagicMock())
    return AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=executor,
        **overrides,
    )


@pytest.mark.asyncio
async def test_auto_busy_input_mode_steer() -> None:
    bus = _make_bus()
    router = _make_router(bus=bus)

    chat_id = "chat-steer-1"
    channel = "telegram"
    session_key = routing_session_key(channel, chat_id)

    steering_token = SteeringToken()
    current_task = asyncio.current_task()
    assert current_task is not None

    active_task = _ActiveTask(
        task=current_task,
        cancel_token=CancellationToken(),
        channel=channel,
        chat_id=chat_id,
        placeholder_id=None,
        started_at=0.0,
        steering_token=steering_token,
        busy_input_mode="steer",
    )
    router._active_tasks[session_key] = active_task

    msg = InboundMessage(
        channel=channel,
        sender_id="user-1",
        content="filter only 2026 data",
        chat_id=chat_id,
        message_id="msg-101",
    )

    # Inbound consumer iteration
    bus.consume_inbound = AsyncMock(side_effect=[msg, TimeoutError])
    with pytest.raises(TimeoutError):
        await router._consume_inbound()

    # Verify steering_token received the message
    assert steering_token.has_pending
    msgs = steering_token.activate()
    assert "filter only 2026 data" in msgs


@pytest.mark.asyncio
async def test_auto_busy_input_mode_redirect() -> None:
    bus = _make_bus()
    router = _make_router(bus=bus)

    chat_id = "chat-redirect-1"
    channel = "telegram"
    session_key = routing_session_key(channel, chat_id)

    steering_token = SteeringToken()
    current_task = asyncio.current_task()
    assert current_task is not None

    active_task = _ActiveTask(
        task=current_task,
        cancel_token=CancellationToken(),
        channel=channel,
        chat_id=chat_id,
        placeholder_id=None,
        started_at=0.0,
        steering_token=steering_token,
        busy_input_mode="redirect",
    )
    router._active_tasks[session_key] = active_task

    msg = InboundMessage(
        channel=channel,
        sender_id="user-1",
        content="stop and refocus immediately",
        chat_id=chat_id,
        message_id="msg-102",
    )

    bus.consume_inbound = AsyncMock(side_effect=[msg, TimeoutError])
    with pytest.raises(TimeoutError):
        await router._consume_inbound()

    # Verify redirect was triggered
    assert steering_token.has_pending
    assert steering_token.redirect_requested
