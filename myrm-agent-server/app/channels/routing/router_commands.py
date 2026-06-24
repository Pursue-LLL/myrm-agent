"""Inbound control commands: /stop, approvals, /new, /compact, /retry, /undo, /goal, /steer, /queue, /memory, /learn, topic commands.

[INPUT]
- channels.protocols.goal_command::GoalSubcommand (POS: parsed /goal subcommand actions)
- channels.routing.commands::TopicCommand, handle_compact, handle_new_session, handle_retry, handle_topic_command, handle_undo (POS: slash command argument parsing and handling)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types)

[OUTPUT]
- RouterCommandsMixin: mixin providing all slash command handler methods for AgentRouter

[POS]
RouterCommandsMixin composed into AgentRouter (router.py) via multiple inheritance;
methods constrain self via RouterCommandsHost. Task/approval session keys use
router_keys.routing_session_key. Logger name is consistent with the router package.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import TYPE_CHECKING

from app.ai_agents.personality_templates import PERSONALITY_TEMPLATES

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager
from app.channels.i18n import get_text
from app.channels.protocols.goal_command import GoalSubcommand
from app.channels.routing.commands import (
    ApprovalDecision,
    TopicCommand,
    handle_compact,
    handle_new_session,
    handle_retry,
    handle_topic_command,
    handle_undo,
    parse_memory_args,
)
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage, OutboundMessage

_ALL_PERSONALITY_KEYS: frozenset[str] = frozenset(PERSONALITY_TEMPLATES.keys())

logger = logging.getLogger("app.channels.routing.router")


class RouterCommandsMixin:
    """Mixin: task cancellation and slash-command handlers from the consume loop."""

    async def _cancel_active_task(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Cancel the active agent task for the sender's chat session."""
        chat_id = msg.chat_id or msg.sender_id
        key = f"{msg.channel}:{chat_id}"
        active = self._active_tasks.pop(key, None)

        if not active:
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

        active.cancel_token.cancel("User /stop command")
        if not active.task.done():
            active.task.cancel()

        if active.placeholder_id:
            await self._fx.cleanup_placeholder(
                active.channel,
                active.chat_id,
                active.placeholder_id,
                get_text(msg, "placeholder_stopped"),
            )

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

    async def _handle_new_session(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /new command: mark peer so next message creates a fresh Chat."""
        await handle_new_session(msg, self._bus, self._new_session_peers)

    async def _handle_compact(self: RouterCommandsHost, msg: InboundMessage, raw_args: str = "") -> None:
        """Handle /compact command: compress chat context to reduce token cost."""
        await handle_compact(
            msg,
            self._bus,
            self._resolver,
            self._compact_handler,
            focus_topic=raw_args.strip(),
        )

    async def _handle_retry(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /retry command: delete last assistant turn and re-execute with original query."""
        retried_msg = await handle_retry(msg, self._bus, self._resolver, self._retry_handler)
        if retried_msg is not None:
            self._gate.submit(retried_msg)

    async def _handle_undo(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /undo command: delete the entire last turn."""
        await handle_undo(msg, self._bus, self._resolver, self._undo_handler)

    async def _handle_topic_command(self: RouterCommandsHost, msg: InboundMessage, cmd: TopicCommand) -> None:
        """Handle /bind, /unbind, /topic commands for topic management."""
        await handle_topic_command(msg, cmd, self._bus, self._topic_resolver)

    async def _handle_yolo_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        action: tuple[str, int | None],
    ) -> None:
        """Handle /yolo command: toggle YOLO mode for this session."""
        from app.channels.routing.router_keys import (
            routing_session_key,
        )

        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        action_type, timeout = action

        if action_type == "status":
            yolo_state = self._session_yolo.get(session_key)
            if yolo_state is None:
                content = get_text(msg, "yolo_off")
            else:
                enabled_at, timeout_val = yolo_state
                if timeout_val:
                    elapsed = time.time() - enabled_at
                    remaining = timeout_val - elapsed
                    if remaining > 0:
                        content = get_text(msg, "yolo_on_expires", seconds=int(remaining))
                    else:
                        del self._session_yolo[session_key]
                        content = get_text(msg, "yolo_off_expired")
                else:
                    content = get_text(msg, "yolo_on_no_expiration")

            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        if action_type == "toggle":
            if session_key in self._session_yolo:
                del self._session_yolo[session_key]
                content = get_text(msg, "yolo_disabled")
            else:
                self._session_yolo[session_key] = (time.time(), None)
                content = get_text(msg, "yolo_activated")

        elif action_type == "on":
            self._session_yolo[session_key] = (time.time(), timeout)
            if timeout:
                content = get_text(msg, "yolo_activated_timeout", timeout=timeout)
            else:
                content = get_text(msg, "yolo_activated")

        elif action_type == "off":
            if session_key in self._session_yolo:
                del self._session_yolo[session_key]
                content = get_text(msg, "yolo_disabled")
            else:
                content = get_text(msg, "yolo_already_off")

        else:
            content = get_text(msg, "yolo_invalid")

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    _DEFAULT_PERSONALITY_STYLES: frozenset[str] = frozenset(_ALL_PERSONALITY_KEYS)
    _DEFAULT_STYLE = "professional"

    async def _handle_personality_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        style: str,
    ) -> None:
        """Handle /personality command: switch session personality style."""
        from myrm_agent_harness.utils.locale import is_chinese

        from app.channels.i18n import resolve_message_locale
        from app.channels.routing.router_keys import (
            routing_session_key,
        )

        provider = self._personality_provider
        locale = resolve_message_locale(msg)
        zh = is_chinese(locale)

        # Dynamic style discovery: prefer provider, fallback to built-in defaults
        if provider:
            templates = provider.list_all()
            valid_styles = {t.name for t in templates}
            default_style = (
                self._DEFAULT_STYLE
                if self._DEFAULT_STYLE in valid_styles
                else (templates[0].name if templates else self._DEFAULT_STYLE)
            )
        else:
            valid_styles = self._DEFAULT_PERSONALITY_STYLES
            default_style = self._DEFAULT_STYLE

        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        if style == "list":
            if provider:
                lines = [get_text(msg, "personality_header")]
                for t in templates:
                    name = t.display_name_zh if zh else t.display_name
                    desc = t.description_zh if zh else t.description
                    lines.append(f"{t.emoji} **{name}**")
                    lines.append(f" {desc}\n")
                content = "\n".join(lines)
            else:
                content = get_text(msg, "personality_list_fallback") + "\n" + "\n".join(f"- {s}" for s in sorted(valid_styles))

            current = self._session_personality.get(session_key)
            if current:
                content += get_text(msg, "personality_current", style=current)
        elif style in valid_styles:
            if style == default_style:
                self._session_personality.pop(session_key, None)
                content = get_text(msg, "personality_reset")
            else:
                self._session_personality[session_key] = style
                template = provider.get(style) if provider else None
                if template:
                    name = template.display_name_zh if zh else template.display_name
                    desc = template.description_zh if zh else template.description
                    content = get_text(
                        msg,
                        "personality_activated",
                        emoji=template.emoji,
                        name=name,
                        description=desc,
                    )
                else:
                    content = get_text(msg, "personality_set", style=style)
        else:
            content = get_text(msg, "personality_invalid", style=style)

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    async def _handle_steer_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /steer command: inject a new instruction into the running agent mid-execution."""
        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)
        instruction = raw_args.strip()

        if not instruction:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "usage_steer"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        active = self._active_tasks.get(session_key)
        if active and active.steering_token:
            active.steering_token.steer(instruction)
            preview = instruction[:80] + "..." if len(instruction) > 80 else instruction
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "steering_applied", preview=preview),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
        else:
            # Idle fallback: no active task, submit as normal message
            self._gate.submit(dataclasses.replace(msg, content=instruction))

    async def _handle_queue_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /queue command: explicitly queue a task for after the current agent task completes."""
        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)
        task_text = raw_args.strip()

        if not task_text:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "usage_queue"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        queued_msg = dataclasses.replace(msg, content=task_text)
        self._gate.submit(queued_msg)

        active = self._active_tasks.get(session_key)
        if active:
            content = get_text(msg, "queue_queued")
        else:
            content = get_text(msg, "queue_immediate")

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    async def _handle_goal_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /goal command: manage persistent cross-turn goals."""
        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        if not self._goal_handler:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "goal_management_not_available"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        args = raw_args.strip()
        lower = args.lower()

        if not args or lower == "status":
            subcommand = GoalSubcommand.STATUS
            sub_args = ""
        elif lower == "pause":
            subcommand = GoalSubcommand.PAUSE
            sub_args = ""
        elif lower == "resume":
            subcommand = GoalSubcommand.RESUME
            sub_args = ""
        elif lower in {"clear", "stop", "done"}:
            subcommand = GoalSubcommand.CLEAR
            sub_args = ""
        elif lower == "budget" or lower.startswith("budget "):
            subcommand = GoalSubcommand.BUDGET
            sub_args = args[6:].strip()
        elif lower == "constraint" or lower.startswith("constraint "):
            subcommand = GoalSubcommand.CONSTRAINT
            sub_args = args[10:].strip()
        else:
            subcommand = GoalSubcommand.SET
            sub_args = args

        if subcommand == GoalSubcommand.SET and self._active_tasks.get(session_key):
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "agent_is_running_goal"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        content = await self._goal_handler.handle_goal(msg, subcommand, sub_args)

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

        if subcommand == GoalSubcommand.SET:
            kickoff_msg = await self._goal_handler.get_kickoff_message(msg, sub_args)
            if kickoff_msg:
                self._gate.submit(kickoff_msg)

    async def _handle_subgoal_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /subgoal slash command."""
        from app.channels.protocols.goal_command import (
            SubgoalSubcommand,
        )

        if not self._goal_handler:
            await self._bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    recipient_id=msg.chat_id or msg.sender_id,
                    content=get_text(msg, "goal_system_not_configured"),
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
                )
            )
            return

        cmd_parts = raw_args.strip().split(maxsplit=1)
        if not cmd_parts:
            subcommand = SubgoalSubcommand.LIST
            cmd_args = ""
        else:
            first_word = cmd_parts[0].lower()
            try:
                subcommand = SubgoalSubcommand(first_word)
                cmd_args = cmd_parts[1] if len(cmd_parts) > 1 else ""
            except ValueError:
                subcommand = SubgoalSubcommand.ADD
                cmd_args = raw_args.strip()

        reply_content = await self._goal_handler.handle_subgoal(
            msg=msg,
            subcommand=subcommand,
            args=cmd_args,
        )

        if reply_content:
            await self._bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    recipient_id=msg.chat_id or msg.sender_id,
                    content=reply_content,
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
                )
            )

    async def _handle_background_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /background (/btw /bg) command: spawn, list, cancel, or steer background tasks."""
        chat_id = msg.chat_id or msg.sender_id
        handler = self._background_handler

        if not handler:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "background_tasks_not_available"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        args = raw_args.strip()

        if not args:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "usage_btw"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        lower = args.lower()

        if lower == "list":
            tasks = await handler.list_background(msg)
            if not tasks:
                content = get_text(msg, "background_none")
            else:
                lines = [get_text(msg, "background_header") + "\n"]
                for t in tasks:
                    status_icon = {
                        "running": "\u23f3",
                        "completed": "\u2705",
                        "failed": "\u274c",
                        "cancelled": "\u26d4",
                    }.get(t.status, "\u2753")
                    preview = t.prompt[:60] + "..." if len(t.prompt) > 60 else t.prompt
                    lines.append(f"{status_icon} `{t.task_id}` — {preview}")
                content = "\n".join(lines)

            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)

        elif lower.startswith("cancel "):
            task_id = args[7:].strip()
            if not task_id:
                content = get_text(msg, "background_cancel_usage")
            else:
                success = await handler.cancel_background(msg, task_id)
                content = (
                    get_text(msg, "background_cancelled", task_id=task_id)
                    if success
                    else get_text(msg, "background_not_found", task_id=task_id)
                )

            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)

        elif lower.startswith("steer "):
            remainder = args[6:].strip()
            parts = remainder.split(None, 1)
            if len(parts) < 2:
                content = get_text(msg, "background_steer_usage")
            else:
                task_id, instruction = parts
                success = await handler.steer_background(msg, task_id, instruction)
                content = (
                    get_text(msg, "background_steer_ok", task_id=task_id)
                    if success
                    else get_text(msg, "background_steer_fail", task_id=task_id)
                )

            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)

        else:
            try:
                task_id = await handler.spawn_background(msg, args)
                content = get_text(msg, "background_started", task_id=task_id)
            except RuntimeError as e:
                content = str(e)

            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)

    async def _handle_handoff_command(self: RouterCommandsHost, msg: InboundMessage, raw_args: str) -> None:
        """Handle /handoff <target_channel>: transfer conversation to another platform."""
        chat_id = msg.chat_id or msg.sender_id
        target = raw_args.strip()
        if not target:
            content = get_text(msg, "handoff_no_target")
        elif target == msg.channel:
            content = get_text(msg, "handoff_same_channel")
        else:
            from app.core.channel_bridge.turn_handler import _resolve_session_with_agent
            from app.services.chat.chat_service import ChatService
            from app.services.chat.handoff import handoff_chat

            session_key, _ = await _resolve_session_with_agent(msg)
            chat = await ChatService.get_channel_chat_by_key(session_key)
            if not chat:
                content = get_text(msg, "handoff_failed", error="No active session")
            else:
                result = await handoff_chat(chat.id, target)
                if result.success:
                    content = get_text(msg, "handoff_success", target=target)
                elif "not found" in result.error.lower() or "not connected" in result.error.lower():
                    content = get_text(msg, "handoff_channel_not_found", target=target)
                elif "pairing" in result.error.lower():
                    content = get_text(msg, "handoff_no_pairing", target=target)
                else:
                    content = get_text(msg, "handoff_failed", error=result.error)

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    async def _handle_status_command(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /status command: show current session status without interrupting agent."""
        chat_id = msg.chat_id or msg.sender_id
        session_key = routing_session_key(msg.channel, chat_id)

        lines: list[str] = [get_text(msg, "status_header") + "\n"]

        provider = self._status_provider
        if provider:
            status = await provider.get_session_status(msg.channel, chat_id)
            if status:
                lines.append(get_text(msg, "status_session", session_id=status.session_id[:12]))
                if status.title:
                    lines.append(get_text(msg, "status_title", title=status.title))
                if status.created_at:
                    lines.append(get_text(msg, "status_created", created_at=status.created_at))
                if status.last_activity:
                    lines.append(
                        get_text(
                            msg,
                            "status_last_activity",
                            last_activity=status.last_activity,
                        )
                    )
                if status.model_name:
                    lines.append(get_text(msg, "status_model", model_name=status.model_name))
                lines.append(get_text(msg, "status_tokens", total_tokens=f"{status.total_tokens:,}"))
            else:
                lines.append(get_text(msg, "status_no_session"))

        is_running = self._active_tasks.get(session_key) is not None
        lines.append(get_text(msg, "status_agent_running") if is_running else get_text(msg, "status_agent_idle"))

        queued = self._gate.pending_count(session_key)
        if queued > 0:
            lines.append(get_text(msg, "status_queued", count=queued))

        yolo_state = self._session_yolo.get(session_key)
        if yolo_state is not None:
            enabled_at, timeout_val = yolo_state
            if timeout_val:
                remaining = timeout_val - (time.time() - enabled_at)
                if remaining > 0:
                    lines.append(get_text(msg, "status_yolo_expires", seconds=int(remaining)))
                else:
                    del self._session_yolo[session_key]
            else:
                lines.append(get_text(msg, "status_yolo_on"))

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content="\n".join(lines),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    async def _handle_kanban_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /kanban (/kb) command: manage kanban board tasks from IM."""
        chat_id = msg.chat_id or msg.sender_id
        handler = self._kanban_handler

        if not handler:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "kanban_not_available"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        args = raw_args.strip()
        if not args:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "kanban_usage"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        try:
            content = await handler.handle_kanban(msg, args)
        except Exception:
            logger.exception("Kanban command failed: /kanban %s", args)
            content = get_text(msg, "kanban_error")

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    # ── /learn: directed skill learning ─────────────────────────────

    async def _handle_learn_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /learn command: teach the agent a new skill from URL/path/description.

        Empty args are valid — the handler falls back to learning from the
        current conversation history.
        """
        chat_id = msg.chat_id or msg.sender_id
        user_args = raw_args.strip()

        handler = self._learn_handler
        if not handler:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "learn_not_configured"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        learn_msg = await handler(msg, user_args)
        if learn_msg is None:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "learn_failed"),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        self._gate.submit(learn_msg)

    # ── /memory: pending memory approval flow ──────────────────────

    async def _handle_memory_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        raw_args: str,
    ) -> None:
        """Handle /memory command: review and approve/reject pending memory writes."""
        chat_id = msg.chat_id or msg.sender_id
        action, memory_id = parse_memory_args(raw_args)

        try:
            from app.core.memory.adapters.setup import (
                create_memory_manager,
                resolve_context_binding,
            )
            from app.services.agent.platform_config import require_platform_embedding_config

            embedding_cfg = await require_platform_embedding_config()
            manager = await create_memory_manager(
                resolve_context_binding(
                    namespaces=None,
                    agent_id=None,
                    channel_id=None,
                    conversation_id=None,
                    task_id=None,
                ),
                embedding_cfg,
                approval_required=True,
            )
        except Exception:
            logger.exception("Failed to create MemoryManager for /memory command")
            content = get_text(msg, "memory_unavailable")
            await self._bus.publish_outbound(OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            ))
            return

        try:
            if action == "pending":
                records = await manager.list_pending(limit=20)
                if not records:
                    content = get_text(msg, "memory_no_pending")
                else:
                    lines: list[str] = [get_text(msg, "memory_pending_header", count=len(records))]
                    for rec in records:
                        short_id = rec.id[:8]
                        lines.append(f"  `{short_id}` [{rec.memory_type.value}] {rec.content[:60]}")
                    lines.append("")
                    lines.append(get_text(msg, "memory_pending_hint"))
                    content = "\n".join(lines)

            elif action == "approve" and memory_id:
                matched = await _resolve_pending_id(manager, memory_id)
                if not matched:
                    content = get_text(msg, "memory_not_found", id=memory_id)
                else:
                    await manager.approve(matched)
                    content = get_text(msg, "memory_approved", id=matched[:8])

            elif action == "reject" and memory_id:
                matched = await _resolve_pending_id(manager, memory_id)
                if not matched:
                    content = get_text(msg, "memory_not_found", id=memory_id)
                else:
                    await manager.reject(matched)
                    content = get_text(msg, "memory_rejected", id=matched[:8])

            elif action == "approve_all":
                records = await manager.list_pending()
                if not records:
                    content = get_text(msg, "memory_no_pending")
                else:
                    for rec in records:
                        await manager.approve(rec.id)
                    content = get_text(msg, "memory_approved_all", count=len(records))
            else:
                content = get_text(msg, "memory_no_pending")

        except Exception:
            logger.exception("Memory command failed: /memory %s", raw_args)
            content = get_text(msg, "memory_error")

        await self._bus.publish_outbound(OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        ))


async def _resolve_pending_id(
    manager: MemoryManager,
    partial_id: str,
) -> str | None:
    """Resolve a partial memory ID prefix to a full pending ID."""
    records = await manager.list_pending()
    for rec in records:
        if rec.id.startswith(partial_id):
            return rec.id
    return None
