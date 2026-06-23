"""iMessage inbound message parsing — webhook payload to InboundMessage.

[POS]
Stateless parsing logic for BlueBubbles webhook data.
"""

from __future__ import annotations

from collections.abc import Callable

from app.channels.types import InboundMessage, MediaAttachment

from .helpers import TAPBACK_CODE_TO_EMOJI, mime_to_media_type

InboundBuilder = Callable[..., InboundMessage]


def parse_message(
    data: dict[str, object],
    api_url: str,
    password: str,
    build_inbound: InboundBuilder,
) -> InboundMessage | None:
    """Parse a BlueBubbles message payload into an InboundMessage."""
    if data.get("isFromMe", False):
        return None

    handle = data.get("handle", {})
    sender = str(handle.get("address", "")) if isinstance(handle, dict) else ""

    chats = data.get("chats")
    chat_guid = sender
    if isinstance(chats, list) and chats:
        first_chat = chats[0]
        if isinstance(first_chat, dict):
            chat_guid = str(first_chat.get("guid", sender))

    msg_guid = str(data.get("guid", ""))
    is_group = ";+;" in chat_guid

    reaction_msg = _parse_tapback(data, sender, chat_guid, is_group, build_inbound)
    if reaction_msg:
        return reaction_msg

    content = str(data.get("text", "") or "")
    reply_to = str(data.get("threadOriginatorGuid", "") or "")

    media_list: list[MediaAttachment] = []
    attachments = data.get("attachments", [])
    if isinstance(attachments, list):
        for att in attachments:
            if not isinstance(att, dict):
                continue
            mime = str(att.get("mimeType", ""))
            mt = mime_to_media_type(mime)
            att_guid = str(att.get("guid", ""))
            url = f"{api_url}/api/v1/attachment/{att_guid}/download?password={password}" if att_guid else None
            transfer_name = att.get("transferName")
            fname = str(transfer_name) if transfer_name else None
            media_list.append(
                MediaAttachment(
                    media_type=mt,
                    url=url,
                    filename=fname,
                    mime_type=mime,
                )
            )

    if not content.strip() and not media_list:
        return None

    return build_inbound(
        sender_id=sender,
        content=content.strip(),
        chat_id=chat_guid,
        is_group=is_group,
        mentioned=False,
        media=tuple(media_list),
        message_id=msg_guid,
        reply_to_id=reply_to or None,
    )


def _parse_tapback(
    data: dict[str, object],
    sender: str,
    chat_guid: str,
    is_group: bool,
    build_inbound: InboundBuilder,
) -> InboundMessage | None:
    """Detect and parse iMessage Tapback reactions from BlueBubbles webhook data."""
    assoc_type = data.get("associatedMessageType")
    if not isinstance(assoc_type, (int, float)):
        return None
    assoc_type_int = int(assoc_type)

    if not (2000 <= assoc_type_int < 3000):
        return None

    assoc_guid = str(data.get("associatedMessageGuid", "") or "")
    if assoc_guid.startswith("p:"):
        parts = assoc_guid.split("/", 1)
        assoc_guid = parts[1] if len(parts) > 1 else assoc_guid

    if not assoc_guid:
        return None

    emoji = TAPBACK_CODE_TO_EMOJI.get(assoc_type_int, "")
    if not emoji:
        return None

    return build_inbound(
        sender_id=sender,
        content=emoji,
        chat_id=chat_guid,
        is_group=is_group,
        mentioned=True,
        message_id=assoc_guid,
        metadata={"reaction": True, "target_message_id": assoc_guid},
    )
