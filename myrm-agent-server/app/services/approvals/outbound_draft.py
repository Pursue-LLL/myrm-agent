"""Lifecycle of a held channel reply (an ``outbound_draft`` approval) once someone has decided on it.

[INPUT]
- app.database.models.approval::ApprovalRecord (POS: persisted approval record)
- app.core.channel_bridge::get_channel_gateway (POS: channel gateway singleton; its bus publishes messages)
- app.channels.routing.message_effects::MessageEffects (POS: placeholder cleanup shared with the router)
- app.channels.i18n::channel_t (POS: localized channel copy catalog)
- app.core.channel_bridge.locale_provider::resolve_user_locale (POS: the owner's language preference)
- app.services.event.app_event_bus::AppEvent (POS: server event bus feeding toasts and IM notifications)
- app.services.infra.system_notification::SystemNotificationService (POS: persisted notification center entries)

[OUTPUT]
- finalize_outbound_draft: the one terminal step for a decided draft (send or release it, close the sender's
  "awaiting review" placeholder, tell the owner when an approved reply did not go out)
- send_outbound_draft_payload: rebuild and publish the held reply
- discard_outbound_draft_payload: release the temp attachments of a reply that will never be sent
- draft_code, DRAFT_CODE_MIN_CHARS: how a held reply is named in chat (review requests print it, ``/draft`` reads it)

[POS]
Every way of deciding on a held reply (WebUI, IM button, owner command, batch, TTL sweeper) ends in
``ApprovalRegistry``, which calls ``finalize_outbound_draft`` once the PENDING -> decided transition is committed.
Keeping the send, the release and the sender-side cleanup here means no resolver can forget one of them.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import TYPE_CHECKING

from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

if TYPE_CHECKING:
    from app.channels.types import OutboundMessage
    from app.database.models.approval import ApprovalRecord

logger = logging.getLogger(__name__)

# What the sender's chat is left with: the invisible text the router also leaves for a reply that is never shown.
_CLOSED_PLACEHOLDER_TEXT = "\u200b"
_PLACEHOLDER_CLOSE_TIMEOUT_S = 10.0

# In chat a held reply is named by the first characters of its approval id. Review requests print
# ``_DRAFT_CODE_CHARS`` of them; a command may shorten that no further than ``DRAFT_CODE_MIN_CHARS``, so that a typo
# is unlikely to land on another reply.
_DRAFT_CODE_CHARS = 8
DRAFT_CODE_MIN_CHARS = 6


def draft_code(approval_id: str) -> str:
    """The short code that names a held reply in a review request and in ``/draft``."""
    return approval_id[:_DRAFT_CODE_CHARS]


async def finalize_outbound_draft(record: ApprovalRecord) -> None:
    """Carry out the decision on a held reply. Never raises: the decision is already committed.

    Approved: publish the reply, and tell the owner when it could not go out. Rejected or expired: release its
    temp attachments. Either way the "awaiting review" placeholder the router left in the sender's chat is closed.
    """
    payload = record.payload or {}
    if record.status == "APPROVED":
        if not await _send(payload, record):
            await _notify_owner_not_sent(payload, record.id)
    else:
        discard_outbound_draft_payload(payload, record.id)
    await _close_placeholder(payload, record.id)


async def _send(payload: dict[str, object], record: ApprovalRecord) -> bool:
    try:
        return await send_outbound_draft_payload(payload, record.agent_id, record.id)
    except Exception:
        logger.exception("Outbound draft %s could not be sent", record.id[:12])
        return False


def _decode_held_reply(payload: dict[str, object], record_id: str) -> OutboundMessage | None:
    """Rebuild the reply a draft holds (its text lives in ``draft_content``); None without a readable snapshot."""
    from app.channels.types import OutboundMessage

    snapshot = payload.get("outbound")
    if not isinstance(snapshot, dict):
        return None
    try:
        return OutboundMessage.from_dict(snapshot)
    except Exception:
        logger.warning("Outbound draft %s has an unreadable message snapshot", record_id[:12], exc_info=True)
        return None


async def send_outbound_draft_payload(
    payload: dict[str, object],
    agent_id: str | None,
    record_id: str,
) -> bool:
    """Publish the reply a draft approval holds, carrying the (possibly edited) reviewed text.

    The reply goes out exactly as the agent produced it (attachments, buttons, thread); ``agent_id`` only stands in
    for an unknown owner. Returns True if the message was sent, False if skipped (no readable snapshot, or nothing
    to send).
    """
    from app.core.channel_bridge import get_channel_gateway

    held = _decode_held_reply(payload, record_id)
    if held is None:
        logger.warning("Outbound draft %s send skipped: no readable message snapshot", record_id[:12])
        return False

    content = str(payload.get("draft_content", ""))
    if not content.strip() and not held.media:
        logger.warning("Outbound draft %s send skipped: empty content", record_id[:12])
        return False

    outbound = dataclasses.replace(held, content=content, user_id=held.user_id or agent_id or "system")
    await get_channel_gateway().publish(outbound)
    logger.info("Outbound draft %s sent", record_id[:12])
    return True


def discard_outbound_draft_payload(payload: dict[str, object], record_id: str) -> None:
    """Release the temp attachments of a draft that will never be sent (rejected or expired)."""
    from app.channels.core.outbound_media import discard_ephemeral_media

    held = _decode_held_reply(payload, record_id)
    if held is not None:
        discard_ephemeral_media(held.media)


async def _close_placeholder(payload: dict[str, object], record_id: str) -> None:
    """Close the "awaiting review" placeholder the router left in the sender's chat when it held the reply.

    Left alone it would stay for good: a rejected or expired reply would read as one still on its way, and an
    approved one would sit next to the reply it announced. Best effort and bounded, so a slow platform never stalls
    the resolver that triggered the decision.
    """
    channel, chat_id, placeholder_id = payload.get("channel"), payload.get("recipient_id"), payload.get("placeholder_id")
    if not (isinstance(channel, str) and isinstance(chat_id, str) and isinstance(placeholder_id, str) and placeholder_id):
        return
    try:
        from app.channels.routing.message_effects import MessageEffects
        from app.core.channel_bridge import get_channel_gateway

        effects = MessageEffects(get_channel_gateway().bus)
        await asyncio.wait_for(
            effects.cleanup_placeholder(channel, chat_id, placeholder_id, _CLOSED_PLACEHOLDER_TEXT),
            timeout=_PLACEHOLDER_CLOSE_TIMEOUT_S,
        )
    except Exception:
        logger.warning("Outbound draft %s: could not close the review placeholder", record_id[:12], exc_info=True)


async def _notify_owner_not_sent(payload: dict[str, object], record_id: str) -> None:
    """Report an approved reply that did not go out: approving it promised the sender would get it.

    Reaches the owner as the same error toast and IM notice a permanently failed delivery raises, and as an entry
    in the notification center for when nobody was looking.
    """
    try:
        from app.channels.i18n import channel_t
        from app.core.channel_bridge.locale_provider import resolve_user_locale
        from app.services.infra.system_notification import SystemNotificationService

        locale = await resolve_user_locale()
        title = str(channel_t(locale, "draft_not_sent_title"))
        body = str(channel_t(locale, "draft_not_sent_body"))

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.MESSAGE_DEAD_LETTERED,
                data={"channel": str(payload.get("channel") or ""), "error_reason": body, "delivery_id": ""},
            )
        )
        await SystemNotificationService.create_notification(
            title=title,
            message=body,
            type="error",
            source="outbound_draft",
            meta_data={"approval_id": record_id},
        )
    except Exception:
        logger.warning("Outbound draft %s: could not notify the owner of the unsent reply", record_id[:12], exc_info=True)
