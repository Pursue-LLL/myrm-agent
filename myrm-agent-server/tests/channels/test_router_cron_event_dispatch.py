"""Integration tests for cron event dispatch hook placement, sender admission and sender trust in AgentRouter."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, PairingRole, PairingStatus
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import InboundMessage

_ADMIN_PAIRING = (PairingStatus.ACTIVE, PairingRole.ADMIN, None)


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


def _pairing_store(*, identity: str | None = None, row: tuple[PairingStatus, PairingRole, int | None] | None = None) -> MagicMock:
    """A pairing store that knows the one sender: its resolved ``identity`` and its pairing ``row``, if it has them."""
    pairing = MagicMock()
    pairing.resolve = AsyncMock(return_value=identity)
    pairing.get_pairing_detail = AsyncMock(return_value=row)
    return pairing


@pytest.fixture()
def router(bus: MagicMock) -> AgentRouter:
    """A router whose sender is the owner: an ACTIVE admin pairing."""
    return AgentRouter(
        bus=bus,
        pairing_store=_pairing_store(identity="sandbox", row=_ADMIN_PAIRING),
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
                untrusted=False,
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


def _dm_from(sender_id: str, content: str, *, message_id: str) -> InboundMessage:
    """A DM whose sender the router has not resolved yet, as the adapters deliver it."""
    return InboundMessage(
        channel="feishu",
        sender_id=sender_id,
        chat_id=sender_id,
        content=content,
        metadata={"message_id": message_id},
        message_id=message_id,
    )


def _dm_router(
    bus: MagicMock,
    *,
    policy: DmPolicy = DmPolicy.ALLOWLIST,
    identity: str | None = None,
    row: tuple[PairingStatus, PairingRole, int | None] | None = None,
) -> AgentRouter:
    """A router with the given DM ``policy`` whose pairing store knows the one sender as ``identity`` / ``row``."""
    policy_provider = MagicMock()
    policy_provider.get_dm_policy = AsyncMock(return_value=policy)
    return AgentRouter(
        bus=bus,
        pairing_store=_pairing_store(identity=identity, row=row),
        agent_executor=AsyncMock(),
        policy_provider=policy_provider,
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )


async def _deliver(router: AgentRouter, *messages: InboundMessage) -> AsyncMock:
    """Route the messages through the real consume loop and return the patched event dispatch."""
    dispatch = AsyncMock(return_value=0)
    with (
        patch("app.channels.routing.router.dispatch_cron_event_for_inbound_message", dispatch),
        patch.object(router._gate, "submit"),
    ):
        await router.start()
        try:
            for msg in messages:
                await router._bus._handle_inbound(msg)
                await asyncio.sleep(0.15)
        finally:
            await router.stop()
    return dispatch


@pytest.mark.asyncio
async def test_sender_the_policy_ignores_does_not_fire_event_triggers(bus: MagicMock) -> None:
    router = _dm_router(bus)

    dispatch = await _deliver(router, _dm_from("stranger", "server down alert", message_id="stranger-1"))

    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_paired_member_fires_fenced_event_triggers(bus: MagicMock) -> None:
    router = _dm_router(bus, identity="paired_member_feishu_member", row=(PairingStatus.ACTIVE, PairingRole.MEMBER, None))

    dispatch = await _deliver(router, _dm_from("member", "server down alert", message_id="member-1"))

    dispatch.assert_awaited_once_with("server down alert", "feishu", "", untrusted=True)


@pytest.mark.asyncio
async def test_owner_fires_unfenced_event_triggers(bus: MagicMock) -> None:
    router = _dm_router(bus, identity="sandbox", row=_ADMIN_PAIRING)

    dispatch = await _deliver(router, _dm_from("owner", "server down alert", message_id="owner-dm-1"))

    dispatch.assert_awaited_once_with("server down alert", "feishu", "", untrusted=False)


@pytest.mark.asyncio
async def test_open_policy_guest_fires_fenced_event_triggers(bus: MagicMock) -> None:
    router = _dm_router(bus, policy=DmPolicy.OPEN)

    dispatch = await _deliver(router, _dm_from("guest", "server down alert", message_id="guest-1"))

    dispatch.assert_awaited_once_with("server down alert", "feishu", "", untrusted=True)


@pytest.mark.asyncio
async def test_failed_admission_check_skips_dispatch_and_keeps_routing(
    router: AgentRouter, caplog: pytest.LogCaptureFixture
) -> None:
    check = AsyncMock(side_effect=[RuntimeError("store down"), True])
    with (
        patch.object(router._resolver, "is_sender_admitted", check),
        caplog.at_level(logging.WARNING, logger="app.channels.routing.router"),
    ):
        dispatch = await _deliver(router, _msg("first alert", message_id="fail-1"), _msg("second alert", message_id="fail-2"))

    dispatch.assert_awaited_once_with("second alert", "feishu", "owner-1", untrusted=False)
    assert "Admission check failed for feishu/user1, denying" in caplog.text


@pytest.mark.asyncio
async def test_failed_trust_check_fences_the_job_and_keeps_routing(router: AgentRouter, caplog: pytest.LogCaptureFixture) -> None:
    check = AsyncMock(side_effect=RuntimeError("store down"))
    with (
        patch.object(router._resolver, "is_untrusted_event_sender", check),
        caplog.at_level(logging.WARNING, logger="app.channels.routing.router"),
    ):
        dispatch = await _deliver(router, _msg("server alert", message_id="trust-1"))

    dispatch.assert_awaited_once_with("server alert", "feishu", "owner-1", untrusted=True)
    assert "Trust check failed for feishu/user1, treating as untrusted" in caplog.text
