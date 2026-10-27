"""Router stop mixin: /stop, and the session abort that /stop and /new share.

[INPUT]
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_state_key, routing_session_key (POS: channel+peer+topic state-map key and chat-wide key formats.)
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: approval timeout scheduling)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)
- channels.i18n::get_text (POS: multi-language gateway command replies and system-generated channel messages.)

[OUTPUT]
- RouterCommandsStopMixin: _abort_session_task (ends a session's turn and the timeout of an approval it waits on), /stop (the chat's turn first, then the sender's delegated tasks; the reply names the delegated tasks)

[POS]
Router stop mixin segment. Cancels the active turn of a session, or the delegated tasks the sender started from the
chat, and tells the sender which one it stopped.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.i18n import get_text
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key, routing_state_key
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger("app.channels.routing.router")


def _task_labels(task_ids: list[str]) -> str:
    """Delegated task ids the way the chat shows them: ``[abc123], [def456]``."""
    return ", ".join(f"[{task_id}]" for task_id in task_ids)


class RouterCommandsStopMixin:
    """Mixin: /stop and the session abort shared with /new."""

    async def _abort_session_task(
        self: RouterCommandsHost,
        state_key: str,
        reason: str,
        placeholder_text: str | None = None,
    ) -> bool:
        """Cancel the active agent task and clean up session state.

        Shared by ``/stop`` and ``/new`` to avoid duplicated cancel logic.
        Returns True when a task was actually cancelled.
        """
        active = self._active_tasks.pop(state_key, None)
        if active is None:
            return False

        if self._approval_msg_ids.pop(state_key, None) is not None:
            # The session was waiting on an approval; its timeout guard would otherwise resume the session the
            # user just ended. The guard is keyed by chat, so only a session that itself waits may end it.
            ApprovalTimeoutScheduler.get().cancel(routing_session_key(active.channel, active.chat_id))

        active.cancel_token.cancel(reason)
        if not active.task.done():
            active.task.cancel()

        if active.placeholder_id and placeholder_text:
            await self._fx.cleanup_placeholder(
                active.channel,
                active.chat_id,
                active.placeholder_id,
                placeholder_text,
            )

        return True

    async def _cancel_active_task(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Cancel the active agent task for the sender's chat session.

        A turn of the chat is stopped first. Only when none is running does ``/stop`` reach the background tasks the
        sender delegated from this chat, so one command never ends both a conversation turn and a long task.
        """
        chat_id = msg.chat_id or msg.sender_id
        user_id = msg.user_id or msg.sender_id
        state_key = routing_state_key(msg.channel, chat_id, msg.thread_id)

        stopped_turn = await self._abort_session_task(
            state_key,
            reason="User /stop command",
            placeholder_text=get_text(msg, "placeholder_stopped"),
        )
        stopped_tasks: list[str] = []
        if stopped_turn:
            # A delegated task is not part of the turn, so the stop did not reach it: say which one still runs.
            running = self._delegation_coordinator.running_task_ids(msg.channel, chat_id, user_id)
            text = (
                get_text(msg, "execution_stopped_background_running", task_ids=_task_labels(running))
                if running
                else get_text(msg, "execution_stopped")
            )
        else:
            stopped_tasks = self._delegation_coordinator.cancel_for_chat(msg.channel, chat_id, user_id)
            text = (
                get_text(msg, "delegation_stopped", task_ids=_task_labels(stopped_tasks))
                if stopped_tasks
                else get_text(msg, "no_active_task_to_stop")
            )

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=text,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)
        if stopped_turn or stopped_tasks:
            logger.warning("AgentRouter: /stop cancelled task for %s/%s", msg.channel, chat_id)
