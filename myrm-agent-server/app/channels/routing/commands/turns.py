"""[INPUT]
- app.channels.i18n::get_text (POS: Provides multi-language support for gateway slash command replies and system-generated channel messages (not Agent LLM output).)
- app.channels.types::InboundMessage / OutboundMessage (POS: Channel system domain types — pure data definitions, no I/O.)

[OUTPUT]
- _format_file_revert_notice: _format_file_revert_notice
- _publish_outbound_notice: _publish_outbound_notice
- handle_retry: Handle /retry command: delete last assistant turn and return original query for re-execution.
- handle_undo: Handle /undo command: delete the entire last turn (user + assistant messages).

[POS]
IM 斜杠命令域的子模块；由 app/channels/routing/commands/__init__.py 聚合导出。
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.turn_management import (
        RetryHandler,
        UndoHandler,
    )
    from app.channels.routing.policy_resolver import (
        PolicyResolver,
    )

logger = logging.getLogger(__name__)


def _format_file_revert_notice(
    msg: InboundMessage,
    *,
    reverted_count: int,
    files_not_revertible: int,
    reverted_key: str,
    not_revertible_key: str,
) -> str | None:
    lines: list[str] = []
    if reverted_count > 0:
        lines.append(get_text(msg, reverted_key, count=reverted_count))
    if files_not_revertible > 0:
        lines.append(get_text(msg, not_revertible_key, count=files_not_revertible))
    return "\n".join(lines) if lines else None


async def _publish_outbound_notice(
    msg: InboundMessage,
    bus: MessageBus,
    *,
    content: str,
) -> None:
    peer_id = msg.chat_id or msg.sender_id
    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)


async def handle_retry(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    retry_handler: RetryHandler | None = None,
) -> InboundMessage | None:
    """Handle /retry command: delete last assistant turn and return original query for re-execution.

    Returns an InboundMessage with the original query if retry succeeded (router should
    re-dispatch), or None if no re-execution is needed.
    """
    peer_id = msg.chat_id or msg.sender_id

    if not retry_handler:
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=get_text(msg, "retry_not_configured"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return None

    try:
        if msg.is_group:
            resolved = await resolver.resolve_group_user(msg)
            if not resolved:
                return None
            user_id, resolved_msg = resolved
            msg = resolved_msg
        else:
            dm_uid = await resolver.resolve_dm_user(msg)
            if not dm_uid:
                return None
            user_id = dm_uid

        result = await retry_handler(msg, user_id)

        if result.success and result.query:
            revert_notice = _format_file_revert_notice(
                msg,
                reverted_count=result.reverted_count,
                files_not_revertible=result.files_not_revertible,
                reverted_key="retry_reverted",
                not_revertible_key="retry_files_not_revertible",
            )
            if revert_notice:
                await _publish_outbound_notice(msg, bus, content=revert_notice)
            return dataclasses.replace(msg, content=result.query)

        if result.deleted_count == 0:
            content = get_text(msg, "retry_nothing")
        else:
            content = get_text(msg, "retry_failed")
    except Exception as exc:
        logger.warning("AgentRouter: /retry failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "retry_failed_error", error="internal error")

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)
    return None


async def handle_undo(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    undo_handler: UndoHandler | None = None,
) -> None:
    """Handle /undo command: delete the entire last turn (user + assistant messages)."""
    peer_id = msg.chat_id or msg.sender_id

    if not undo_handler:
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=get_text(msg, "undo_not_configured"),
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

        result = await undo_handler(msg, user_id)

        if result.success:
            if result.deleted_count > 0:
                content = get_text(msg, "undo_success", count=result.deleted_count)
                revert_notice = _format_file_revert_notice(
                    msg,
                    reverted_count=result.reverted_count,
                    files_not_revertible=result.files_not_revertible,
                    reverted_key="undo_reverted",
                    not_revertible_key="undo_files_not_revertible",
                )
                if revert_notice:
                    content = f"{content}\n{revert_notice}"
            else:
                content = get_text(msg, "undo_nothing")
        else:
            content = get_text(msg, "undo_failed")
    except Exception as exc:
        logger.warning("AgentRouter: /undo failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "undo_failed_error", error="internal error")

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)
