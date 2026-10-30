"""The router answers the bus's sender gate with the verdict it gives a message from that sender.

A channel that asks about a sender outside its inbound pipeline (a Discord slash command) must get the verdict a
message from that sender would get: the enabled groups, the guest mode, and the owner who is always admitted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.protocols.pairing import GroupPolicy, PairingRole, PairingStatus
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage

_ENABLED_CHAT = "enabled-chat"


class _Channel(BaseChannel):
    name = "gate-test"

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


def _msg(*, chat_id: str, sender_id: str = "member") -> InboundMessage:
    return InboundMessage(
        channel="gate-test", sender_id=sender_id, user_id=sender_id, chat_id=chat_id, content="/act", is_group=True
    )


def _router(bus: MessageBus, *, owner: str = "owner") -> AgentRouter:
    policy = MagicMock()
    policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
    policy.get_enabled_groups = AsyncMock(return_value={_ENABLED_CHAT})
    policy.get_guest_mode = AsyncMock(return_value=False)

    async def pairing_detail(channel: str, sender_id: str) -> tuple[PairingStatus, PairingRole] | None:
        return (PairingStatus.ACTIVE, PairingRole.ADMIN) if sender_id == owner else None

    pairing = MagicMock()
    pairing.get_pairing_detail = AsyncMock(side_effect=pairing_detail)
    return AgentRouter(bus=bus, pairing_store=pairing, agent_executor=MagicMock(), policy_provider=policy)


async def test_a_channel_registered_before_the_router_gets_the_routers_verdict() -> None:
    bus = MessageBus()
    channel = _Channel()
    bus.register_channel(channel)
    _router(bus)

    assert await channel.is_sender_admitted(_msg(chat_id=_ENABLED_CHAT)) is True
    assert await channel.is_sender_admitted(_msg(chat_id="other-chat")) is False


async def test_the_owner_is_admitted_in_a_chat_the_policy_does_not_enable() -> None:
    bus = MessageBus()
    channel = _Channel()
    _router(bus)
    bus.register_channel(channel)

    assert await channel.is_sender_admitted(_msg(chat_id="other-chat", sender_id="owner")) is True


async def test_a_failing_policy_denies() -> None:
    bus = MessageBus()
    channel = _Channel()
    bus.register_channel(channel)
    router = _router(bus)
    router._resolver.is_sender_admitted = AsyncMock(side_effect=RuntimeError("policy store down"))  # type: ignore[method-assign]

    assert await channel.is_sender_admitted(_msg(chat_id=_ENABLED_CHAT)) is False
