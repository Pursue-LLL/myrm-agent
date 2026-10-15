"""Inbound risk gate of the channel router.

[INPUT]
- services.risk.ingress::screen_user_text (POS: 用户键入文字的风险闸门入口)
- channels.core.bus::MessageBus (POS: async message bus)
- channels.i18n::channel_t, resolve_message_locale (POS: channel reply copy in the sender's language)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types)

[OUTPUT]
- hold_risky_inbound: screens one piece of text a sender typed; when a rule holds it, tells the sender and returns True

[POS]
Every place the router hands a sender's text to an agent (a new turn, a steer or redirect into a running one, a delegated
task) asks this gate first, so a message that one path would hold is held on all of them. The caller drops the text when
this returns True; the reply is one fixed notice, in the sender's language, that names no rule.
"""

from __future__ import annotations

import logging

from app.channels.core.bus import MessageBus
from app.channels.i18n import channel_t, resolve_message_locale
from app.channels.types import InboundMessage, OutboundMessage
from app.services.risk.ingress import screen_user_text

logger = logging.getLogger("app.channels.routing.router")


async def hold_risky_inbound(bus: MessageBus, msg: InboundMessage, text: str | None) -> bool:
    """Whether a risk rule holds *text*, which *msg*'s sender typed; if so the sender has been told."""
    result = await screen_user_text(text, session_id=msg.sender_id)
    if result is None:
        return False

    await bus.publish_outbound(
        OutboundMessage(
            channel=msg.channel,
            recipient_id=(msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id),
            content=channel_t(resolve_message_locale(msg), "risk_inbound_blocked"),
            user_id=msg.user_id or "",
            reply_to_id=msg.message_id,
        )
    )
    logger.info(
        "Inbound risk gate blocked message on channel '%s' from '%s': rules=%s",
        msg.channel,
        msg.sender_id,
        [m.display_name for m in result.matches],
    )
    return True
