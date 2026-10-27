"""Router command dispatch mixin: from a resolved slash command to the handler that runs it.

[INPUT]
- channels.routing.pipeline.hosts::RouterCommandDispatchHost (POS: typing protocol for the host attributes and handlers this mixin calls)
- channels.routing.command_defs::CommandAction, CommandDef, CommandKind (POS: slash command data model and enums)
- channels.routing.command_registry::ResolvedCommand (POS: central O(1) command lookup result)
- channels.routing.commands::parse_personality_args, parse_topic_args, parse_yolo_args (POS: slash command argument parsing)
- channels.routing.inbound_risk_gate::hold_risky_inbound (POS: risk screening of a sender's text before any agent reads it)
- channels.i18n::get_text, resolve_message_locale (POS: localized channel copy)
- channels.types::InboundMessage, OutboundMessage (POS: channel message envelopes)

[OUTPUT]
- RouterCommandDispatchMixin: ``_dispatch_resolved`` (owner check, risk screening, then system / agent-route / skill), ``_dispatch_system_command`` (action to handler), the ``!shell`` migration reply, skill-bound commands and ``/help``

[POS]
Command-dispatch segment of ``AgentRouter``. The handlers it starts live in the ``commands`` subpackage (``RouterCommandsMixin``); this mixin only decides which one runs.
"""

from __future__ import annotations

import asyncio

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.routing.command_defs import CommandAction, CommandDef, CommandKind
from app.channels.routing.command_registry import ResolvedCommand
from app.channels.routing.commands import parse_personality_args, parse_topic_args, parse_yolo_args
from app.channels.routing.inbound_risk_gate import hold_risky_inbound
from app.channels.routing.pipeline.hosts import RouterCommandDispatchHost
from app.channels.types import InboundMessage, OutboundMessage


class RouterCommandDispatchMixin:
    """Mixin: owner check, risk screening and the action-to-handler table of slash commands."""

    async def _dispatch_resolved(
        self: RouterCommandDispatchHost,
        msg: InboundMessage,
        resolved: ResolvedCommand,
    ) -> bool:
        """Dispatch a resolved command to its handler. Returns True if consumed."""
        cmd = resolved.command_def
        action = cmd.action

        if cmd.owner_only and not await self._check_admin_permission(msg):
            chat_id = msg.chat_id or msg.sender_id
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "permission_denied", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            asyncio.create_task(self._bus.publish_outbound(reply))
            return True

        if cmd.kind == CommandKind.SYSTEM and action is not None:
            # System commands act on their text directly (a background task, a goal, a kanban card, a steer), so they
            # are screened here; agent-route and skill commands reach the gated agent path instead.
            if await hold_risky_inbound(self._bus, msg, resolved.raw_args):
                return True
            return await self._dispatch_system_command(msg, action, resolved.raw_args)

        if cmd.kind == CommandKind.AGENT_ROUTE:
            self._gate.submit(msg)
            return True

        if cmd.kind == CommandKind.SKILL:
            asyncio.create_task(self._handle_skill_command(msg, cmd, resolved.raw_args))
            return True

        return False

    async def _dispatch_system_command(
        self: RouterCommandDispatchHost,
        msg: InboundMessage,
        action: CommandAction,
        raw_args: str,
    ) -> bool:
        """Dispatch a system command by action type. Returns True if consumed."""
        if action == CommandAction.STOP:
            asyncio.create_task(self._cancel_active_task(msg))
            return True

        if action == CommandAction.NEW_SESSION:
            asyncio.create_task(self._handle_new_session(msg))
            return True

        if action == CommandAction.COMPACT:
            asyncio.create_task(self._handle_compact(msg, raw_args))
            return True

        if action == CommandAction.RETRY:
            asyncio.create_task(self._handle_retry(msg))
            return True

        if action == CommandAction.UNDO:
            asyncio.create_task(self._handle_undo(msg))
            return True

        if action == CommandAction.YOLO:
            parsed = parse_yolo_args(raw_args)
            if parsed:
                asyncio.create_task(self._handle_yolo_command(msg, parsed))
            else:
                chat_id = msg.chat_id or msg.sender_id
                reply = OutboundMessage(
                    channel=msg.channel,
                    recipient_id=chat_id,
                    content=get_text(msg, "yolo_invalid_usage"),
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
                )
                asyncio.create_task(self._bus.publish_outbound(reply))
            return True

        if action == CommandAction.PERSONALITY:
            style = parse_personality_args(raw_args)
            asyncio.create_task(self._handle_personality_command(msg, style))
            return True

        if action in (CommandAction.BIND, CommandAction.UNBIND, CommandAction.TOPIC):
            action_name = action.value
            topic_cmd = parse_topic_args(action_name, raw_args)
            asyncio.create_task(self._handle_topic_command(msg, topic_cmd))
            return True

        if action == CommandAction.DRAFT:
            asyncio.create_task(self._handle_draft_command(msg, raw_args))
            return True

        if action == CommandAction.GOAL:
            asyncio.create_task(self._handle_goal_command(msg, raw_args))
            return True

        if action == CommandAction.SUBGOAL:
            asyncio.create_task(self._handle_subgoal_command(msg, raw_args))
            return True

        if action == CommandAction.STEER:
            asyncio.create_task(self._handle_steer_command(msg, raw_args))
            return True

        if action == CommandAction.QUEUE:
            asyncio.create_task(self._handle_queue_command(msg, raw_args))
            return True

        if action == CommandAction.BACKGROUND:
            asyncio.create_task(self._handle_background_command(msg, raw_args))
            return True

        if action == CommandAction.KANBAN:
            asyncio.create_task(self._handle_kanban_command(msg, raw_args))
            return True

        if action == CommandAction.MEMORY:
            asyncio.create_task(self._handle_memory_command(msg, raw_args))
            return True

        if action == CommandAction.LEARN:
            asyncio.create_task(self._handle_learn_command(msg, raw_args))
            return True

        if action == CommandAction.HANDOFF:
            asyncio.create_task(self._handle_handoff_command(msg, raw_args))
            return True

        if action == CommandAction.STATUS:
            asyncio.create_task(self._handle_status_command(msg))
            return True

        if action == CommandAction.QUOTA:
            asyncio.create_task(self._handle_quota_command(msg))
            return True

        if action == CommandAction.HELP:
            asyncio.create_task(self._handle_help_command(msg))
            return True

        return False

    @staticmethod
    def _is_bang_command(content: str | None) -> bool:
        """Return True if content is an unsupported CLI shell command (e.g. !sh, !bash, !cmd)."""
        if not content:
            return False
        trimmed = content.strip()
        if not trimmed:
            return False
        # Only intercept explicit raw shell execution syntax, avoiding group prefixes like !ai, !ask
        first_word = trimmed.split()[0].lower() if trimmed.split() else ""
        if first_word in (
            "!sh",
            "!bash",
            "!exec",
            "!cmd",
            "!shell",
            "！sh",
            "！bash",
            "！exec",
            "！cmd",
            "！shell",
        ):
            return True
        return False

    async def _handle_bang_command(self: RouterCommandDispatchHost, msg: InboundMessage) -> None:
        """Fast-path honest migration reply for !shell CLI commands."""
        chat_id = msg.chat_id or msg.sender_id
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=get_text(msg, "bang_command_unsupported"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)

    async def _handle_skill_command(
        self: RouterCommandDispatchHost,
        msg: InboundMessage,
        cmd: CommandDef,
        raw_args: str,
    ) -> None:
        """Handle a skill-bound slash command (single or bundle)."""
        chat_id = msg.chat_id or msg.sender_id

        if not self._skill_command_handler or not cmd.skill_ids:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "skill_not_configured", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        skill_msg = await self._skill_command_handler(msg, cmd.skill_ids, raw_args, cmd.instruction)
        if skill_msg is None:
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=get_text(msg, "skill_load_failed", cmd=cmd.name),
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await self._bus.publish_outbound(reply)
            return

        self._gate.submit(skill_msg)

    async def _handle_help_command(self: RouterCommandDispatchHost, msg: InboundMessage) -> None:
        """Handle /help command: show available commands."""
        chat_id = msg.chat_id or msg.sender_id
        locale = resolve_message_locale(msg)
        lines = self._registry.help_lines(locale, owner=await self._check_admin_permission(msg))
        content = get_text(msg, "help_header") + "\n" + "\n".join(lines)
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)
