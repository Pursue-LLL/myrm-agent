"""InboundMessage and PolicyResolver builders shared by the PolicyResolver test files."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import InboundMessage


def make_message(
    content: str = "hi",
    *,
    channel: str = "test",
    sender_id: str = "u1",
    chat_id: str = "",
    is_group: bool = False,
    mentioned: bool = False,
    user_id: str = "",
    metadata: dict[str, object] | None = None,
    thread_id: str = "",
    is_bot: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        mentioned=mentioned,
        user_id=user_id,
        metadata=metadata or {},
        thread_id=thread_id,
        is_bot=is_bot,
    )


def make_resolver(
    *,
    pairing: MagicMock | None = None,
    policy: MagicMock | None = None,
    get_channel: MagicMock | None = None,
) -> PolicyResolver:
    if pairing is None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()

    fx = MagicMock(spec=MessageEffects)
    fx.send_pending_reply = AsyncMock()
    fx.send_pairing_request_reply = AsyncMock()
    fx.send_mute_reply = AsyncMock()

    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_free_response_chats", None), AsyncMock)
    ):
        policy.get_free_response_chats = AsyncMock(return_value=set())
    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_guest_mode", None), AsyncMock)
    ):
        policy.get_guest_mode = AsyncMock(return_value=False)
    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_enabled_groups", None), AsyncMock)
    ):
        policy.get_enabled_groups = AsyncMock(return_value=set())

    return PolicyResolver(
        pairing=pairing,
        policy=policy,
        context_buffer=GroupContextBuffer(),
        fx=fx,
        get_channel=get_channel or MagicMock(return_value=None),
    )
