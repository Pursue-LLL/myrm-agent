"""Matrix inbound event handlers and sync loop.

[INPUT]
- mautrix.client::Client (POS: mautrix Matrix client, dispatches events)
- channels.providers.matrix.html (POS: Mention stripping utilities)

[OUTPUT]
- register_event_handlers: Wire up mautrix event handlers on a Client
- handle_room_message: Process m.room.message events into InboundMessage
- handle_reaction: Process m.reaction annotation events into InboundMessage
- handle_invite: Auto-join invited rooms
- run_sync_loop: Background /sync loop with error recovery

[POS]
Event handling for MatrixChannel. Processes inbound m.room.message events
(text, image, audio, video, file), parses relations (reply-to, thread),
identifies DMs vs group chats via DM cache, and runs the continuous /sync loop.
"""

from __future__ import annotations

import asyncio
import logging

from app.channels.providers.matrix.html import (
    strip_matrix_mention,
)
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
)

logger = logging.getLogger(__name__)


def register_event_handlers(
    client: object,
    on_room_message: object,
    on_invite: object,
    on_reaction: object | None = None,
) -> None:
    """Register mautrix event handlers for inbound messages, reactions, invites."""
    from mautrix.client import Client
    from mautrix.client import InternalEventType as IntEvt
    from mautrix.client.dispatcher import MembershipEventDispatcher
    from mautrix.types import EventType

    if not isinstance(client, Client):
        return

    client.add_dispatcher(MembershipEventDispatcher)
    client.add_event_handler(EventType.ROOM_MESSAGE, on_room_message)
    if callable(on_reaction):
        client.add_event_handler(EventType.REACTION, on_reaction)
    client.add_event_handler(IntEvt.INVITE, on_invite)


async def handle_room_message(
    event: object,
    *,
    user_id: str,
    dm_rooms: dict[str, bool],
    encryption: bool,
    build_inbound_fn: object,
    emit_inbound_fn: object,
) -> None:
    """Process m.room.message events from mautrix Client sync.

    Parses text, media, relations, and DM context, then emits an InboundMessage.
    """
    room_id = str(getattr(event, "room_id", ""))
    sender = str(getattr(event, "sender", ""))
    event_id = str(getattr(event, "event_id", ""))

    if sender == user_id:
        return

    content_obj = getattr(event, "content", None)
    if content_obj is None:
        return

    msg_type = str(getattr(content_obj, "msgtype", ""))
    body = str(getattr(content_obj, "body", ""))

    content = ""
    media_list: list[MediaAttachment] = []

    raw_url = getattr(content_obj, "url", None)
    media_url = str(raw_url) if raw_url else None

    file_info = getattr(content_obj, "file", None)
    if file_info and encryption:
        media_url = str(getattr(file_info, "url", "")) or media_url

    if msg_type == "m.text":
        content = strip_matrix_mention(body, user_id) if user_id else body
    elif msg_type == "m.image":
        media_list.append(
            MediaAttachment(media_type=MediaType.IMAGE, url=media_url, filename=body)
        )
    elif msg_type == "m.audio":
        media_list.append(MediaAttachment(media_type=MediaType.AUDIO, url=media_url))
    elif msg_type == "m.video":
        media_list.append(MediaAttachment(media_type=MediaType.VIDEO, url=media_url))
    elif msg_type == "m.file":
        media_list.append(
            MediaAttachment(media_type=MediaType.DOCUMENT, url=media_url, filename=body)
        )

    if not content.strip() and not media_list:
        return

    relates_to = getattr(content_obj, "relates_to", None)
    reply_to_id = None
    thread_id = None
    if relates_to:
        in_reply = getattr(relates_to, "in_reply_to", None)
        if in_reply:
            reply_to_id = str(getattr(in_reply, "event_id", "")) or None

        rel_type = getattr(relates_to, "rel_type", None)
        if rel_type and str(rel_type) == "m.thread":
            thread_event_id = getattr(relates_to, "event_id", None)
            thread_id = str(thread_event_id) if thread_event_id else None

    is_group = not dm_rooms.get(room_id, False)

    metadata: dict[str, object] = {
        "event_id": event_id,
        "room_id": room_id,
        "msgtype": msg_type,
    }

    if not callable(build_inbound_fn) or not callable(emit_inbound_fn):
        return

    msg = build_inbound_fn(
        sender_id=sender,
        content=content.strip(),
        chat_id=room_id,
        is_group=is_group,
        mentioned=user_id in body if user_id else False,
        media=tuple(media_list),
        reply_to_id=reply_to_id,
        thread_id=thread_id,
        metadata=metadata,
        message_id=event_id,
    )
    await emit_inbound_fn(msg)


_REACTION_EMOJI_MAP: dict[str, str] = {
    "+1": "\U0001F44D",
    "👍": "\U0001F44D",
    "✅": "\u2705",
    "❤": "\u2764",
    "♾️": "\u267E",
    "♾": "\u267E",
    "⭐": "\u2B50",
    "-1": "\U0001F44E",
    "👎": "\U0001F44E",
    "❌": "\u274C",
    "🚫": "\U0001F6AB",
}


async def handle_reaction(
    event: object,
    *,
    user_id: str,
    dm_rooms: dict[str, bool],
    emit_inbound_fn: object,
) -> None:
    """Process ``m.reaction`` annotation events into ``InboundMessage``.

    Matrix reactions arrive as ``m.reaction`` events whose
    ``content.m.relates_to`` references the target ``event_id`` with
    ``rel_type=m.annotation`` and a ``key`` (the emoji or shortcode). We
    forward only events that map cleanly onto the unified Unicode model
    consumed by ``parse_approval_command``; anything else is ignored.
    """
    sender = str(getattr(event, "sender", ""))
    if not sender or sender == user_id:
        return

    room_id = str(getattr(event, "room_id", ""))
    event_id = str(getattr(event, "event_id", ""))

    content_obj = getattr(event, "content", None)
    relates_to = getattr(content_obj, "relates_to", None) if content_obj else None
    if relates_to is None:
        return

    rel_type = str(getattr(relates_to, "rel_type", "") or "")
    if rel_type and rel_type != "m.annotation":
        return

    target_event_id = str(getattr(relates_to, "event_id", "") or "")
    if not target_event_id:
        return

    raw_key = getattr(relates_to, "key", "") or ""
    key = str(raw_key).strip()
    if not key:
        return

    emoji = _REACTION_EMOJI_MAP.get(key, key)

    is_group = not dm_rooms.get(room_id, False)

    if not callable(emit_inbound_fn):
        return

    inbound = InboundMessage(
        channel="matrix",
        sender_id=sender,
        content=emoji,
        chat_id=room_id,
        is_group=is_group,
        mentioned=True,
        message_id=target_event_id,
        metadata={
            "event_id": event_id,
            "room_id": room_id,
            "reaction": True,
            "target_message_id": target_event_id,
        },
    )
    await emit_inbound_fn(inbound)


async def handle_invite(
    event: object,
    client: object,
    auto_join_fn: object,
) -> None:
    """Auto-join rooms we're invited to."""
    room_id = str(getattr(event, "room_id", ""))
    if room_id and client and callable(auto_join_fn):
        await auto_join_fn(client, room_id)


async def auto_join(client: object, room_id: str) -> None:
    """Accept a room invitation."""
    from mautrix.client import Client
    from mautrix.types import RoomID as MxRoomID

    if not isinstance(client, Client):
        return

    try:
        await client.join_room(MxRoomID(room_id))
        logger.info("MatrixChannel: auto-joined room %s", room_id)
    except Exception as exc:
        logger.debug("Matrix auto-join failed for %s: %s", room_id, exc)


async def run_sync_loop(
    client: object,
    status_fn: object,
    auto_join_fn: object,
) -> None:
    """Background sync loop using mautrix Client.

    Args:
        client: mautrix Client instance
        status_fn: Callable returning current ChannelStatus
        auto_join_fn: Callable(client, room_id) for invite processing
    """
    if not client:
        return

    while callable(status_fn) and status_fn() == ChannelStatus.RUNNING:
        try:
            sync_data = await client.sync(timeout=30000)  # type: ignore[union-attr]
            if isinstance(sync_data, dict):
                invites = sync_data.get("rooms", {}).get("invite", {})
                if isinstance(invites, dict) and callable(auto_join_fn):
                    for room_id in invites:
                        await auto_join_fn(client, room_id)

                try:
                    tasks = client.handle_sync(sync_data)  # type: ignore[union-attr]
                    if tasks:
                        await asyncio.gather(*tasks)
                except Exception as exc:
                    logger.warning("Matrix: sync event dispatch error: %s", exc)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            if callable(status_fn) and status_fn() != ChannelStatus.RUNNING:
                break
            logger.warning("MatrixChannel: sync error, retrying in 5s: %s", exc)
            await asyncio.sleep(5.0)
