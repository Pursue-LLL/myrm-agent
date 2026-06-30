"""Integration tests for cron event dispatch hook placement in AgentRouter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import InboundMessage


def _msg(content: str, *, message_id: str = "msg-1") -> InboundMessage:
    return InboundMessage(
        channel="feishu",
        sender_id="user1",
        chat_id="chat1",
        content=content,
        metadata={"message_id": message_id},
        message_id=message_id,
        user_id="owner-1",
    )


@pytest.fixture()
def bus() -> MagicMock:
    from app.channels.core.bus import MessageBus

    real_bus = MessageBus()
    real_bus._ensure_queues()
    bus = MagicMock(wraps=real_bus)
    bus._inbound = real_bus._inbound
    bus.consume_inbound = real_bus.consume_inbound
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


@pytest.fixture()
def router(bus: MagicMock) -> AgentRouter:
    return AgentRouter(
        bus=bus,
        pairing_store=MagicMock(),
        agent_executor=AsyncMock(),
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )


@pytest.mark.asyncio
async def test_normal_message_dispatches_cron_once(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    with (
        patch(
            "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
            dispatch,
        ),
        patch.object(router._gate, "submit"),
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(_msg("server down alert"))
            await asyncio.sleep(0.15)
            dispatch.assert_awaited_once_with(
                "server down alert",
                "feishu",
                "owner-1",
            )
        finally:
            await router.stop()


@pytest.mark.asyncio
async def test_stop_command_skips_cron_dispatch(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    with (
        patch(
            "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
            dispatch,
        ),
        patch.object(router, "_cancel_active_task", new_callable=AsyncMock),
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(_msg("/stop", message_id="stop-1"))
            await asyncio.sleep(0.15)
            dispatch.assert_not_awaited()
        finally:
            await router.stop()


@pytest.mark.asyncio
async def test_pending_approval_skips_cron_dispatch(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    with (
        patch(
            "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
            dispatch,
        ),
        patch.object(router, "_has_pending_approval", return_value=True),
        patch.object(router, "_handle_approval_command", new_callable=AsyncMock),
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(_msg("y", message_id="approve-1"))
            await asyncio.sleep(0.15)
            dispatch.assert_not_awaited()
        finally:
            await router.stop()


@pytest.mark.asyncio
async def test_reaction_skips_cron_dispatch(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    msg = InboundMessage(
        channel="feishu",
        sender_id="user1",
        chat_id="chat1",
        content="👍",
        metadata={"message_id": "react-1", "reaction": True},
        message_id="react-1",
        user_id="owner-1",
    )
    with patch(
        "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
        dispatch,
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(msg)
            await asyncio.sleep(0.15)
            dispatch.assert_not_awaited()
        finally:
            await router.stop()


@pytest.mark.asyncio
async def test_slash_new_skips_cron_dispatch(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    with (
        patch(
            "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
            dispatch,
        ),
        patch.object(router, "_handle_new_session", new_callable=AsyncMock, return_value=None),
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(_msg("/new", message_id="new-1"))
            await asyncio.sleep(0.15)
            dispatch.assert_not_awaited()
        finally:
            await router.stop()


@pytest.mark.asyncio
async def test_duplicate_message_dispatches_cron_once(router: AgentRouter) -> None:
    dispatch = AsyncMock(return_value=0)
    msg = _msg("server alert", message_id="dup-1")
    with (
        patch(
            "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
            dispatch,
        ),
        patch.object(router._gate, "submit"),
    ):
        await router.start()
        try:
            await router._bus._handle_inbound(msg)
            await asyncio.sleep(0.15)
            await router._bus._handle_inbound(msg)
            await asyncio.sleep(0.15)
            assert dispatch.await_count == 1
        finally:
            await router.stop()
