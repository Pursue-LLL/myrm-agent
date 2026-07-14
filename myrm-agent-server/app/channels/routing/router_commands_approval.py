"""Router approval mixin: /stop, reaction/button approval, decision resume payloads.

[INPUT]
- channels.routing.commands::ApprovalDecision (POS: slash command argument parsing and handling.)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)

[OUTPUT]
- RouterCommandsApprovalMixin: _abort_session_task, approval command handlers, decision resume payloads

[POS]
Router approval mixin segment. Cancels active tasks, validates reaction/button
approvals, and builds harness-compatible resume_value for LangGraph interrupt resume.
"""

from __future__ import annotations

import dataclasses
import logging

from app.channels.i18n import get_text
from app.channels.routing.commands import ApprovalDecision
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger("app.channels.routing.router")


class RouterCommandsApprovalMixin:
    """Mixin: /stop, reaction/button approval, and decision resume payloads."""

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

        self._approval_msg_ids.pop(state_key, None)

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
        """Cancel the active agent task for the sender's chat session."""
        chat_id = msg.chat_id or msg.sender_id
        state_key = routing_session_key(msg.channel, chat_id)

        cancelled = await self._abort_session_task(
            state_key,
            reason="User /stop command",
            placeholder_text=get_text(msg, "placeholder_stopped"),
        )

        if not cancelled:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "no_active_task_to_stop"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=get_text(msg, "execution_stopped"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)
        logger.warning("AgentRouter: /stop cancelled task for %s/%s", msg.channel, chat_id)

    def _has_pending_approval(self: RouterCommandsHost, msg: InboundMessage) -> bool:
        """Check if the session has a pending approval request.

        Returns True if there's an active agent task for this session, which may
        be waiting for user approval via interrupt(). Used to gate numeric shortcut
        commands (like plain "1" or "2") to prevent misinterpretation as approval.
        """
        chat_id = msg.chat_id or msg.sender_id
        state_key = routing_session_key(msg.channel, chat_id)
        return self._active_tasks.get(state_key) is not None

    def _is_reaction_approval_valid(self: RouterCommandsHost, msg: InboundMessage) -> bool:
        """Validate an inbound emoji reaction as an approval command.

        Layered checks (a single failure aborts the approval):

        1. **Pending approval gate** — there must be an active agent task
           awaiting an interrupt() resume on this chat. Reactions on stale
           messages are silently dropped.
        2. **Target match** — when ``target_message_id`` is present in the
           reaction metadata it must equal the stored approval message id;
           otherwise the reaction targets some other message (e.g. an old
           bot reply) and is ignored.
        3. **Approver authorisation** — the reacting ``sender_id`` must match
           either the original requester captured on the active task or one of
           the explicitly configured ``approval_co_approvers``. This blocks
           bystanders in group chats from inadvertently or maliciously
           approving someone else's high-privilege action.

        Direct messages (``is_group == False``) skip step 3 because the chat
        is 1:1 with the requester and bystander attacks are impossible.
        """
        chat_id = msg.chat_id or msg.sender_id
        state_key = routing_session_key(msg.channel, chat_id)

        active = self._active_tasks.get(state_key)
        if active is None:
            return False

        target_mid = msg.metadata.get("target_message_id")
        stored_mid = self._approval_msg_ids.get(state_key)
        if target_mid and stored_mid and str(target_mid) != stored_mid:
            return False

        if not msg.is_group:
            return True

        actor = msg.sender_id or ""
        if not actor:
            return False
        if active.requester_id and actor == active.requester_id:
            return True
        if actor in self._approval_co_approvers:
            return True

        logger.info(
            "Reaction approval denied for actor %s on %s/%s (requester=%s, co_approvers=%d)",
            actor,
            msg.channel,
            chat_id,
            active.requester_id,
            len(self._approval_co_approvers),
        )
        return False

    async def _handle_approval_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        decision: ApprovalDecision | list[ApprovalDecision],
    ) -> None:
        """Resume the interrupted agent with the user's three-tier decision.

        Builds a ``resume_value`` payload that mirrors the harness
        ``_batch_decisions`` contract:

        - ``allow_once``   → ``{"type": "approve"}``
        - ``allow_always`` → ``{"type": "approve", "allow_always": True}``
          (harness `add_to_allowlist_if_needed` then persists into the user's
          allowlist; future identical tool invocations bypass ASK gate)
        - ``deny``         → ``{"type": "reject", "feedback": "..."}``

        Supports both single and batch decisions; LangGraph resumes the
        interrupted graph state via ``Command(resume=resume_value)``.
        """
        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        if self._active_tasks.get(session_key) is None:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "no_pending_approval"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        if isinstance(decision, str):
            entry = self._build_decision_entry(decision, msg.channel)
            decisions: list[dict[str, object]] = [entry]
            status_msg = self._status_for_single_decision(msg, decision)
        else:
            decisions = [self._build_decision_entry(d, msg.channel, batch=True) for d in decision]
            status_msg = self._status_for_batch_decision(msg, decision)

        resume_value: dict[str, object] = {"decisions": decisions}

        resume_msg = dataclasses.replace(
            msg,
            resume_value=resume_value,
            metadata={**msg.metadata, "is_resume": True},
        )

        approval_mid = self._approval_msg_ids.pop(session_key, None)
        if approval_mid:
            await self._bus.edit_channel_message(msg.channel, chat_id, approval_mid, status_msg)

        self._gate.submit(resume_msg)

    async def _handle_action_button_approval(
        self: RouterCommandsHost,
        msg: InboundMessage,
    ) -> None:
        """Handle an ActionButton callback for approval (``act:approval:{action}:{id}``).

        Closes the loop between ``ApprovalRegistry.create_approval()`` (which
        pushes ActionButtons to IM channels) and the actual resolution. The
        ``msg.content`` arriving here has the format ``approval:{action}:{id}``
        (the ``act:`` transport prefix is stripped by each channel's inbound parser).

        Steps:
          1. Parse action ("approve" / "deny") and approval_id from content.
          2. Authorise the clicker — only the task's original requester (or a
             co-approver) may resolve; bystanders in group chats get a toast.
          3. Resolve via ``ApprovalRegistry`` (only PENDING records; already-
             resolved approvals return ``None`` and the handler exits).
          4. Edit the original IM message to show the outcome and prevent
             further button clicks from appearing actionable.
          5. Convert the decision into a ``resume_value`` and submit to
             ``SessionGate`` so the interrupted LangGraph agent resumes.
        """
        content = msg.content or ""
        parts = content.split(":", 2)
        if len(parts) != 3 or parts[0] != "approval":
            logger.warning("Malformed action button approval content: %r", content)
            return

        action_raw, approval_id = parts[1], parts[2]
        if action_raw not in ("approve", "deny"):
            logger.warning("Unknown action button approval action: %r", action_raw)
            return

        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        # --- Authorisation (group bystander protection) ---
        active = self._active_tasks.get(session_key)
        if active and msg.is_group:
            actor = msg.sender_id or ""
            requester = active.requester_id or ""
            if actor and requester and actor != requester and actor not in self._approval_co_approvers:
                logger.info(
                    "Action button approval denied: actor=%s requester=%s channel=%s",
                    actor, requester, msg.channel,
                )
                return

        # --- Resolve in DB ---
        from app.services.approvals.registry import ApprovalRegistry

        record = await ApprovalRegistry.resolve_approval(
            approval_id=approval_id,
            decision=action_raw,
        )

        if record is None:
            logger.warning("Action button approval: not found or already resolved id=%s", approval_id[:12])
            return

        logger.info(
            "Action button approval resolved: id=%s action=%s channel=%s sender=%s",
            approval_id[:12], action_raw, msg.channel, msg.sender_id,
        )

        # --- Edit original IM message to show result ---
        origin_message_id = msg.metadata.get("origin_message_id")
        if origin_message_id and chat_id:
            status_icon = "✅" if action_raw == "approve" else "🚫"
            sender_display = msg.metadata.get("username") or msg.sender_id or ""
            status_text = f"{status_icon} {action_raw.title()}d by {sender_display}"
            await self._bus.edit_channel_message(
                msg.channel, chat_id, str(origin_message_id), status_text,
            )

        # --- Outbound draft: send or discard the held message ---
        if record.action_type == "outbound_draft":
            await self._resolve_outbound_draft(record, action_raw)
            return

        # --- Resume the interrupted Agent ---
        if active is not None:
            decision: ApprovalDecision = "allow_once" if action_raw == "approve" else "deny"
            entry = self._build_decision_entry(decision, msg.channel)
            resume_value: dict[str, object] = {"decisions": [entry]}
            resume_msg = dataclasses.replace(
                msg,
                resume_value=resume_value,
                metadata={**msg.metadata, "is_resume": True},
            )
            self._gate.submit(resume_msg)
        else:
            # No active task in router (e.g. Agent resumed via WebUI concurrently).
            # DB is already resolved; publish event for any SSE listeners.
            if record.thread_id:
                from app.services.event.app_event_bus import (
                    AppEvent,
                    AppEventType,
                    get_event_bus,
                )

                bus = get_event_bus()
                bus.publish(
                    AppEvent(
                        event_type=AppEventType.APPROVAL_RESOLVED,
                        data={
                            "action": "resume_agent",
                            "approval_id": record.id,
                            "thread_id": record.thread_id,
                            "chat_id": record.chat_id,
                            "agent_id": record.agent_id,
                            "decision": action_raw,
                        },
                    )
                )

    async def _resolve_outbound_draft(
        self: RouterCommandsHost,
        record: object,
        decision: str,
    ) -> None:
        """Send or discard a held outbound channel draft message."""
        from app.database.models.approval import ApprovalRecord as ApprovalRecordModel

        if not isinstance(record, ApprovalRecordModel):
            return
        if decision == "approve":
            from app.services.approvals.registry import send_outbound_draft_payload

            await send_outbound_draft_payload(record.payload or {}, record.agent_id, record.id)
        else:
            logger.info("Outbound draft %s rejected via channel button, discarded", record.id[:12])

    @staticmethod
    def _build_decision_entry(decision: ApprovalDecision, channel: str, *, batch: bool = False) -> dict[str, object]:
        """Translate the three-tier decision into the harness decision dict.

        The harness ``apply_approval_decisions`` reads ``allowAlways`` from
        ``decision.extensions`` (camelCase) to drive
        ``add_to_allowlist_if_needed``; mirror that contract exactly.
        """
        if decision == "allow_always":
            return {"type": "approve", "extensions": {"allowAlways": True}}
        if decision == "allow_once":
            return {"type": "approve"}
        suffix = "batch command" if batch else "command"
        return {
            "type": "reject",
            "feedback": f"Denied via {channel} channel {suffix}",
        }

    @staticmethod
    def _status_for_single_decision(msg: InboundMessage, decision: ApprovalDecision) -> str:
        if decision == "allow_always":
            return get_text(msg, "approval_always_processing")
        if decision == "allow_once":
            return get_text(msg, "approval_processing")
        return get_text(msg, "approval_denial_processing")

    @staticmethod
    def _status_for_batch_decision(msg: InboundMessage, decisions: list[ApprovalDecision]) -> str:
        approve_count = sum(1 for d in decisions if d != "deny")
        always_count = sum(1 for d in decisions if d == "allow_always")
        reject_count = len(decisions) - approve_count
        if always_count > 0:
            return get_text(
                msg,
                "approval_batch_processing_always",
                approve_count=approve_count,
                always_count=always_count,
                reject_count=reject_count,
            )
        return get_text(
            msg,
            "approval_batch_processing",
            approve_count=approve_count,
            reject_count=reject_count,
        )
