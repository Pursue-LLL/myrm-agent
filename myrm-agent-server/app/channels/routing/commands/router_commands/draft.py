"""Router draft mixin: /draft, deciding on a reply held for review from chat.

[INPUT]
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)
- services.approvals.registry::ApprovalRegistry (POS: unified approval flow scheduler that persists, pushes and resolves approvals; imported lazily in the handler.)
- services.approvals.outbound_draft::DRAFT_CODE_MIN_CHARS, draft_code (POS: how a held reply is named in chat.)

[OUTPUT]
- RouterCommandsDraftMixin: /draft approve|reject <code> handler
- parse_draft_args, DraftAction: pure argument parsing for /draft

[POS]
Router draft mixin segment. Lets the owner decide on a reply held for review from the chat they are already in,
which is the way to do it on channels whose messages carry no approval buttons.
"""

from __future__ import annotations

import logging
from typing import Literal

from app.channels.i18n import get_text
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.types import InboundMessage, OutboundMessage
from app.services.approvals.outbound_draft import DRAFT_CODE_MIN_CHARS, draft_code

logger = logging.getLogger("app.channels.routing.router")

DraftAction = Literal["approve", "reject", "usage"]

_HEX_DIGITS = frozenset("0123456789abcdef")
_DECIDED_KEYS: dict[DraftAction, str] = {"approve": "draft_cmd_approved", "reject": "draft_cmd_rejected"}


def parse_draft_args(raw_args: str) -> tuple[DraftAction, str]:
    """Parse ``/draft approve <code>`` and ``/draft reject <code>`` (``deny`` reads as ``reject``).

    A held reply is only ever decided by an explicit, well-formed code, so anything else, such as a missing,
    too short or non-hex code, an unknown verb or trailing words, yields ``("usage", "")``.
    """
    parts = raw_args.lower().split()
    if len(parts) != 2:
        return "usage", ""
    verb, code = parts
    if len(code) < DRAFT_CODE_MIN_CHARS or not _HEX_DIGITS.issuperset(code):
        return "usage", ""
    if verb == "approve":
        return "approve", code
    if verb in ("reject", "deny"):
        return "reject", code
    return "usage", ""


class RouterCommandsDraftMixin:
    """Mixin: /draft."""

    async def _handle_draft_command(self: RouterCommandsHost, msg: InboundMessage, raw_args: str) -> None:
        """Handle /draft: approve (send) or reject (discard) a reply held for review, then say what happened."""
        action, code = parse_draft_args(raw_args)
        content = await _decide(msg, action, code)
        await self._bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                recipient_id=msg.chat_id or msg.sender_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
        )


async def _decide(msg: InboundMessage, action: DraftAction, code: str) -> str:
    """Apply the decision the owner typed and return the reply to show them."""
    if action == "usage":
        return get_text(msg, "draft_cmd_usage")

    from app.services.approvals.registry import ApprovalRegistry

    try:
        matches = await ApprovalRegistry.find_pending_outbound_drafts(code)
        if len(matches) > 1:
            return get_text(msg, "draft_cmd_ambiguous", code=code)
        record = (
            await ApprovalRegistry.resolve_approval(matches[0].id, "approve" if action == "approve" else "deny")
            if matches
            else None
        )
    except Exception:
        logger.exception("Failed to %s a held reply from /draft", action)
        return get_text(msg, "draft_cmd_error")

    if record is None:
        return get_text(msg, "draft_cmd_not_found", code=code)
    logger.info(
        "Held reply %s decided by /draft: action=%s channel=%s sender=%s", record.id[:12], action, msg.channel, msg.sender_id
    )
    return get_text(msg, _DECIDED_KEYS[action], code=draft_code(record.id))
