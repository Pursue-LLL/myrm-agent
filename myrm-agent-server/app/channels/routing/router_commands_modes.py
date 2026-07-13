"""Router mode mixin: /yolo, /personality, /steer, /queue commands.

[INPUT]
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)
- ai_agents.personality_templates::PERSONALITY_TEMPLATES (POS: built-in personality style catalog.)

[OUTPUT]
- RouterCommandsModesMixin: per-session mode toggles and mid-run steering injection

[POS]
Router mode mixin segment. Manages YOLO auto-approve sessions, personality overrides,
/steer mid-execution injection, and explicit /queue task deferral.
"""

from __future__ import annotations

import dataclasses
import logging
import time

from app.ai_agents.personality_templates import PERSONALITY_TEMPLATES
from app.channels.i18n import get_text
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage, OutboundMessage

_ALL_PERSONALITY_KEYS: frozenset[str] = frozenset(PERSONALITY_TEMPLATES.keys())

logger = logging.getLogger("app.channels.routing.router")

class RouterCommandsModesMixin:
    """Mixin: /yolo, /personality, /steer, /queue commands."""

    async def _handle_yolo_command(
        self: RouterCommandsHost,
        msg: InboundMessage,
        action: tuple[str, int | None],
    ) -> None:
        """Handle /yolo command: toggle YOLO mode for this session."""
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
