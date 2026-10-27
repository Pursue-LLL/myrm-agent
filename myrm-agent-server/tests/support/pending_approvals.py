"""Builders for the router's open approval requests, shared by the channel routing tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.channels.routing.pending_approvals import PendingApproval, PendingApprovals
from app.channels.types import InboundMessage


def asked_in(
    channel: str = "telegram",
    chat_id: str = "c1",
    *,
    thread_id: str | None = None,
    sender_id: str = "u1",
    user_id: str = "u1",
    card_message_id: str = "card-1",
    is_group: bool = False,
    locale: str = "en",
) -> PendingApproval:
    """The approval a turn of ``chat_id`` asked, as the router keeps it."""
    message = InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content="run the build",
        chat_id=chat_id,
        thread_id=thread_id,
        is_group=is_group,
        metadata={"locale": locale},
    )
    return PendingApproval(card_message_id=card_message_id, message=message, user_id=user_id)


def empty_registry() -> PendingApprovals:
    """A registry whose expiry reports go nowhere."""
    return PendingApprovals(on_expire=AsyncMock())


def waiting(state_key: str, card_message_id: str = "card-1") -> PendingApprovals:
    """A registry in which the chat behind ``state_key`` waits on an approval without a time limit."""
    registry = empty_registry()
    channel, _, chat_id = state_key.partition(":")
    registry.register(state_key, asked_in(channel, chat_id, card_message_id=card_message_id), None)
    return registry
