"""[INPUT]
- app.channels.i18n::get_text (POS: Provides multi-language support for gateway slash command replies and)
- app.channels.routing.router_keys::routing_state_key (POS: ``routing_state_key`` builds the key for the router's in-memory state maps. It carries every)
- app.channels.types::InboundMessage / OutboundMessage (POS: Channel system domain types — pure data definitions, no I/O.)

[OUTPUT]
- handle_new_session: Handle /new command: mark peer so next message creates a fresh Chat.
- handle_compact: Handle /compact command: compress chat context to reduce token cost.

[POS]
IM 斜杠命令域的子模块；由 app/channels/routing/commands/__init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.routing.router_keys import routing_state_key
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.compact import CompactHandler
    from app.channels.routing.policy_resolver import (
        PolicyResolver,
    )

logger = logging.getLogger(__name__)


async def handle_new_session(
    msg: InboundMessage,
    bus: MessageBus,
    new_session_peers: dict[str, float],
) -> None:
    """Handle /new command: mark peer so next message creates a fresh Chat."""
    peer_key = routing_state_key(msg.channel, msg.chat_id or msg.sender_id, msg.thread_id)
    new_session_peers[peer_key] = time.monotonic()

    chat_id = msg.chat_id or msg.sender_id
    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=chat_id,
        content=get_text(msg, "new_session_started"),
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=msg.message_id if msg.is_group else None,
    )
    await bus.publish_outbound(reply)


async def handle_compact(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    compact_handler: CompactHandler | None = None,
    *,
    focus_topic: str = "",
) -> None:
    """Handle /compact command: compress chat context to reduce token cost.

    When compact_handler is None, replies with "Compaction not configured."
    Business layer provides CompactHandler to perform DB/chat/compact operations.
    """
    from app.channels.protocols.compact import (
        MAX_FOCUS_TOPIC_LENGTH,
    )

    peer_id = msg.chat_id or msg.sender_id
    effective_topic = focus_topic[:MAX_FOCUS_TOPIC_LENGTH].strip() if focus_topic else ""

    if not compact_handler:
        content = get_text(msg, "compact_not_configured")
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return

    try:
        if msg.is_group:
            resolved = await resolver.resolve_group_user(msg)
            if not resolved:
                return
            user_id, resolved_msg = resolved
            msg = resolved_msg
        else:
            dm_uid = await resolver.resolve_dm_user(msg)
            if not dm_uid:
                return
            user_id = dm_uid

        result = await compact_handler(msg, user_id, focus_topic=effective_topic)

        if result.compacted:
            topic_hint = f" (focus: {effective_topic})" if effective_topic else ""
            content = get_text(
                msg,
                "compact_success",
                message_count=result.message_count,
                tokens_saved=result.tokens_saved,
                topic_hint=topic_hint,
            )
        else:
            content = get_text(msg, "compact_skipped", reason=result.reason or "no action needed")
    except Exception as exc:
        logger.warning("AgentRouter: /compact failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "compact_failed", error="internal error")

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)
