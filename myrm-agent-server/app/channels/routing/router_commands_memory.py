"""Router memory mixin: /status, /kanban, /learn, /memory commands.

[INPUT]
- channels.routing.commands::parse_memory_args (POS: slash command argument parsing and handling.)
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.routing.router_keys::routing_session_key (POS: channel+peer mapping key format.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)
- core.channel_bridge.agent_executor.session::build_channel_budget_key (POS: budget key construction, runtime import in _get_channel_budget_summary.)
- services.budget.channel_budget::get_channel_budget_registry (POS: per-channel budget isolation, runtime import in _get_channel_budget_summary.)

[OUTPUT]
- RouterCommandsMemoryMixin: session status, kanban, directed learning, pending memory approval handlers

[POS]
Router memory mixin segment. Surfaces session diagnostics, kanban IM control,
/learn skill capture kickoff, and /memory pending-write approval workflow.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.routing.commands import parse_memory_args
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger("app.channels.routing.router")


def _get_channel_budget_summary(msg: InboundMessage) -> dict[str, object] | None:
    """Return channel budget status dict if an enabled budget policy exists, else None."""
    try:
        from app.core.channel_bridge.agent_executor.session import build_channel_budget_key
        from app.services.budget.channel_budget import get_channel_budget_registry

        budget_key = build_channel_budget_key(msg)
        if not budget_key:
            return None
        info = get_channel_budget_registry().get_status(budget_key)
        if info and info.get("enabled"):
            return info
        return None
    except Exception:
        return None


class RouterCommandsMemoryMixin:
    """Mixin: /status, /kanban, /learn, /memory commands."""

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
                lines.append(get_text(msg, "status_cost", total_usd=f"{status.total_usd:.4f}"))
                lines.append(get_text(msg, "status_calls", total_calls=status.total_calls))

                budget_info = _get_channel_budget_summary(msg)
                if budget_info:
                    lines.append("")
                    lines.append(get_text(msg, "status_budget_header"))
                    lines.append(
                        get_text(
                            msg,
                            "status_budget_today",
                            today_cost=f"{budget_info['today_cost_usd']:.4f}",
                            daily_limit=f"{budget_info['daily_limit_usd']:.2f}",
                            usage_pct=budget_info["usage_pct"],
                        )
                    )
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
