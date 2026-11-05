"""Router approval-end mixin: how an open approval request ends when no person answers it.

[INPUT]
- channels.routing.pending_approvals::PendingApproval, session_agent_id (POS: the open approval request that ends; the agent session a turn runs in.)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_models::_RouterExecutionContext (POS: the prepared turn a request may be superseded by.)
- channels.types::OutboundMessage (POS: channel message type.)
- channels.i18n::get_text (POS: multi-language gateway command replies and system-generated channel messages.)

[OUTPUT]
- RouterCommandsApprovalEndMixin: ``_resume_after_approval_timeout`` (the registry's expiry callback) and
  ``_retire_open_approval`` (a turn about to run in the session a request waits in)

[POS]
Router approval-end mixin segment. When nobody answers in time the registry's timer calls
``_resume_after_approval_timeout``, which tells the chat the outcome and resumes the run through the ``SessionGate``
like any answered request. A new turn in the session a request waits in takes the run behind it away, so
``_retire_open_approval`` ends the request with a notice instead of leaving a card whose answer nobody receives.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.routing.pending_approvals import PendingApproval, session_agent_id
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.types import OutboundMessage

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.routing.router_models import _RouterExecutionContext

logger = logging.getLogger("app.channels.routing.router")


async def _show_on_approval_card(bus: MessageBus, pending: PendingApproval, text_key: str) -> None:
    """Say ``text_key`` where the request was asked: on its card, or as a message when the channel has no card to edit."""
    msg = pending.message
    chat_id = msg.chat_id or msg.sender_id
    notice = get_text(msg, text_key)
    shown = bool(pending.card_message_id) and await bus.edit_channel_message(
        msg.channel, chat_id, pending.card_message_id, notice
    )
    if not shown:
        await bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=notice,
                user_id=pending.user_id,
                thread_id=msg.thread_id,
            )
        )


class RouterCommandsApprovalEndMixin:
    """Mixin: the ways an open approval request ends without a person's answer (timeout, superseded by a new turn)."""

    async def _resume_after_approval_timeout(
        self: RouterCommandsHost,
        state_key: str,
        pending: PendingApproval,
        resume_value: dict[str, object],
    ) -> None:
        """No one answered the approval in time: say what the timeout decided and resume the run as an ordinary turn.

        The resumed run is a router turn like one a person answered, so ``/stop`` reaches it and its reply is
        delivered the same way. The outcome replaces the approval card, or is sent as a message when the channel
        returned no card id or cannot edit.
        """
        resume_msg = pending.resume_message(resume_value)
        outcome_key = "approval_timeout_approved" if resume_value.get("decision") == "approve" else "approval_timeout_denied"
        await _show_on_approval_card(self._bus, pending, outcome_key)

        # The turn that asked kept its entry only to keep the approval answerable; the resumed turn takes its place.
        entry = self._active_tasks.get(state_key)
        if entry is not None and entry.task.done():
            del self._active_tasks[state_key]
        self._gate.submit(resume_msg)

    async def _retire_open_approval(self: RouterCommandsHost, ctx: _RouterExecutionContext) -> None:
        """A turn is about to run in the session an approval waits in: the request ends, with a notice on its card.

        Input that reaches a session takes the run suspended at the approval away, so a later answer would be
        delivered to nobody while the card, the timer and a bare ``1`` or ``2`` still looked like an open question.
        A turn of another agent runs in another session and leaves the request alone.
        """
        pending = self._pending_approvals.get(ctx.state_key)
        if pending is None or pending.agent_id != session_agent_id(ctx.topic_ctx):
            return
        self._pending_approvals.pop(ctx.state_key)
        try:
            await _show_on_approval_card(self._bus, pending, "approval_superseded")
        except Exception:
            # The turn that superseded the request must still run.
            logger.warning("Superseded approval card of %s could not be updated", ctx.state_key, exc_info=True)
