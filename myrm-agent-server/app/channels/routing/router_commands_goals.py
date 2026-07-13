"""Router goals mixin: /goal, /subgoal, /background, /handoff commands.

[INPUT]
- channels.protocols.goal_command::GoalSubcommand (POS: parsed /goal subcommand actions.)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)

[OUTPUT]
- RouterCommandsGoalsMixin: goal lifecycle, background tasks, and cross-channel handoff handlers

[POS]
Router goals mixin segment. Delegates persistent goals, subgoals, background
spawn/list/cancel/steer, and /handoff platform transfer to business handlers.
"""

from __future__ import annotations

import logging

from app.channels.i18n import get_text
from app.channels.protocols.goal_command import GoalSubcommand
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger("app.channels.routing.router")

class RouterCommandsGoalsMixin:
    """Mixin: /goal, /subgoal, /background, /handoff commands."""

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
