"""Router delegation mixin: launching a delegated task and handing its tool approvals to the chat.

[INPUT]
- channels.delegation::build_delegation_task (POS: task factory for a delegated request)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_state_key (POS: channel+peer+topic state-map key format)
- channels.routing.router_models::_ActiveTask (POS: the router's record of a task that waits for or runs a turn)
- channels.types::InboundMessage, OutboundMessage, ProgressUpdate (POS: channel message types.)

[OUTPUT]
- RouterCommandsDelegationMixin: the ``/delegate`` launch with its receipt, and the approval hand-over of a delegated run.

[POS]
Delegated tasks run in the background and stay out of ``_active_tasks`` so the chat remains free; the one moment they
enter it is a tool approval, where the chat's ``/approve``, approval buttons and reactions must find the pending request.
"""

from __future__ import annotations

import asyncio
import functools
import time

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.channels.delegation import build_delegation_task
from app.channels.i18n import get_text, resolve_message_locale
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.router_models import _ActiveTask
from app.channels.types import InboundMessage, OutboundMessage, ProgressUpdate


class RouterCommandsDelegationMixin:
    """Mixin: delegated task launch and approval hand-over for AgentRouter."""

    async def _handle_delegation_inbound(self: RouterCommandsHost, msg: InboundMessage, clean_prompt: str) -> bool:
        """Handle mobile task delegation: issue sub-second receipt and launch background task."""
        chat_id = msg.chat_id or msg.sender_id
        user_id = msg.user_id or chat_id
        if not self._delegation_guard.can_accept(msg.channel, user_id):
            reject_msg = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "delegation_quota_reached", limit=self._delegation_guard.max_active),
                user_id=user_id,
                thread_id=msg.thread_id,
            )
            await self._bus.publish_outbound(reject_msg)
            return True

        task = build_delegation_task(
            origin_channel=msg.channel,
            origin_user_id=user_id,
            origin_chat_id=chat_id,
            prompt=clean_prompt,
        )
        self._delegation_coordinator.register_task(task)
        self._delegation_guard.acquire(msg.channel, user_id, task.task_id)

        receipt_outbound = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=get_text(msg, "delegation_receipt", task_id=task.task_id, prompt=clean_prompt[:120]),
            user_id=user_id,
            thread_id=msg.thread_id,
            metadata={"delegation_task_id": task.task_id, "is_receipt": True},
        )
        await self._bus.publish_outbound(receipt_outbound)

        async def _run_bg() -> None:
            try:
                await self._delegation_coordinator.execute_task_lifecycle(
                    task,
                    self._executor,
                    self._bus,
                    msg,
                    hand_over_approval=functools.partial(self._hand_over_delegated_approval, msg),
                )
            finally:
                self._delegation_guard.release(msg.channel, user_id, task.task_id)

        asyncio.create_task(_run_bg())
        return True

    async def _hand_over_delegated_approval(
        self: RouterCommandsHost,
        msg: InboundMessage,
        progress: ProgressUpdate,
    ) -> None:
        """Put a delegated run's tool approval in front of its chat so the chat's answer resumes it.

        The run's stream has ended at the approval, which leaves the chat in the state a foreground turn leaves:
        the prompt's message id plus an entry for the finished task, which ``/approve``, the approval buttons and
        reactions look up. The answer then resumes the run's thread as an ordinary turn. An entry of a turn that is
        still running keeps its place: its cleanup retains it while the message id is set.
        """
        chat_id = msg.chat_id or msg.sender_id
        state_key = routing_state_key(msg.channel, chat_id, msg.thread_id)
        approval_message_id = await self._send_interactive_progress(msg, chat_id, progress)
        self._approval_msg_ids[state_key] = approval_message_id or ""

        entry = self._active_tasks.get(state_key)
        if entry is None or entry.task.done():
            runner = asyncio.current_task()
            assert runner is not None
            self._active_tasks[state_key] = _ActiveTask(
                task=runner,
                cancel_token=CancellationToken(),
                channel=msg.channel,
                chat_id=chat_id,
                placeholder_id=None,
                started_at=time.monotonic(),
                requester_id=msg.sender_id or "",
                locale=resolve_message_locale(msg),
            )
