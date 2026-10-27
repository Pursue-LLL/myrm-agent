"""Resolve an inbound IM message to the Web chat that carries its goal.

[INPUT]
- app.channels.types::InboundMessage, SessionKey (POS)
- app.services.chat.chat_service::ChatService (POS: channel chat lookup)

[OUTPUT]
- resolve_chat_id: DB chat id of the channel peer, or None before the first interaction

[POS]
The one place that maps a channel peer to the chat whose goals ``/goal`` commands act on.
"""

from __future__ import annotations

from app.channels.types import InboundMessage, SessionKey


async def resolve_chat_id(msg: InboundMessage) -> str | None:
    """Resolve channel message to DB chat_id via ChatService.

    Builds a SessionKey (matching agent executor convention) and queries the
    Chat table to find the latest chat_id for this channel peer. Returns None
    if no chat exists yet (first interaction).
    """
    peer_kind = "group" if msg.is_group else "dm"
    peer_id = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
    if not peer_id:
        peer_id = f"channel-{msg.channel}"

    sk = SessionKey(
        channel=msg.channel,
        peer_kind=peer_kind,
        peer_id=peer_id,
        thread_id=msg.thread_id,
    )
    base_key = sk.to_str()

    from app.services.chat.chat_service import ChatService

    chat = await ChatService.get_channel_chat_by_key(base_key)
    if chat:
        return chat.id

    newest = await ChatService.get_newest_channel_chat_under(base_key)
    return newest.id if newest is not None else None
