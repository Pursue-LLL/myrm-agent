"""[INPUT]
- app.channels.i18n::get_text (POS: Provides multi-language support for gateway slash command replies and)
- app.channels.types::InboundMessage / OutboundMessage (POS: Channel system domain types — pure data definitions, no I/O.)

[OUTPUT]
- TopicCommand: Parsed topic management command.
- parse_topic_args: Parse topic command arguments from resolved command.
- handle_topic_command: Handle /bind, /unbind, /topic commands for topic/channel management.

[POS]
IM 斜杠命令域的子模块；由 app/channels/routing/commands/__init__.py 聚合导出。
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Literal

from app.channels.i18n import get_text
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.topic import TopicManager

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True, slots=True)
class TopicCommand:
    """Parsed topic management command."""

    action: Literal["bind", "unbind", "topic"]
    agent_id: str | None = None
    project_id: str | None = None
    authorized_path: str | None = None
    clear_workspace: bool = False
    identity_name: str | None = None
    identity_scope: str | None = None


def parse_topic_args(action: str, raw_args: str) -> TopicCommand:
    """Parse topic command arguments from resolved command.

    Supports:
    - legacy bare agent id/name: ``/bind my-agent``
    - key/value pairs: ``/bind agent=my-agent workspace=project:uuid``
    - path workspace: ``/bind workspace=/path/to/vault``
    - team identity: ``/bind agent=my-agent identity=义父 identity_scope=shared``
      (multi-word names need quotes: ``identity="Yi Fu"``).
    """
    agent_id: str | None = None
    project_id: str | None = None
    authorized_path: str | None = None
    clear_workspace = False
    legacy_agent: str | None = None
    identity_name: str | None = None
    identity_scope: str | None = None

    if action == "bind" and raw_args.strip():
        import shlex

        try:
            parts = shlex.split(raw_args.strip())
        except ValueError:
            parts = raw_args.strip().split()
        seen_identity_kv = False
        for part in parts:
            lowered = part.lower()
            if lowered.startswith("agent="):
                value = part.split("=", 1)[1].strip()
                agent_id = value or None
            elif lowered.startswith("identity="):
                seen_identity_kv = True
                value = part.split("=", 1)[1].strip()
                identity_name = value or None
            elif lowered.startswith("identity_scope="):
                seen_identity_kv = True
                value = part.split("=", 1)[1].strip().lower()
                identity_scope = value or None
            elif lowered.startswith("workspace="):
                value = part.split("=", 1)[1].strip()
                if not value or value.lower() in {"none", "clear"}:
                    clear_workspace = True
                elif value.lower().startswith("project:"):
                    project_id = value.split(":", 1)[1].strip() or None
                else:
                    authorized_path = value
            elif "=" not in part and legacy_agent is None and not seen_identity_kv:
                # Bare words after identity=* are name fragments, never an agent.
                # (Multi-word names need quoting at the caller; unquoted tails
                # are dropped instead of hijacking the agent binding.)
                legacy_agent = part

        if agent_id is None and legacy_agent:
            agent_id = legacy_agent

    return TopicCommand(
        action=action,
        agent_id=agent_id,
        project_id=project_id,
        authorized_path=authorized_path,
        clear_workspace=clear_workspace,
        identity_name=identity_name,
        identity_scope=identity_scope,
    )


# ---------------------------------------------------------------------------
# Delegated command handlers (called by AgentRouter)
# ---------------------------------------------------------------------------

async def handle_topic_command(
    msg: InboundMessage,
    cmd: TopicCommand,
    bus: MessageBus,
    topic_resolver: TopicManager | None,
) -> None:
    """Handle /bind, /unbind, /topic commands for topic/channel management."""
    chat_id = msg.chat_id or msg.sender_id

    if not topic_resolver:
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=get_text(msg, "topic_not_configured"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return

    scope_name = get_text(msg, "topic_scope_topic") if msg.thread_id else get_text(msg, "topic_scope_channel")

    try:
        if cmd.action == "bind":
            bind_kwargs: dict[str, object] = {
                "channel": msg.channel,
                "chat_id": chat_id,
                "thread_id": msg.thread_id,
            }
            if cmd.agent_id is not None:
                bind_kwargs["agent_id"] = cmd.agent_id
            if cmd.project_id is not None:
                bind_kwargs["project_id"] = cmd.project_id
            if cmd.authorized_path is not None:
                bind_kwargs["authorized_path"] = cmd.authorized_path
            if cmd.clear_workspace:
                bind_kwargs["project_id"] = None
                bind_kwargs["authorized_path"] = None
            if cmd.identity_scope is not None:
                from app.channels.types import IdentityScopeMode

                try:
                    bind_kwargs["identity_scope"] = IdentityScopeMode(cmd.identity_scope)
                except ValueError:
                    raise ValueError(f"Invalid identity_scope '{cmd.identity_scope}'; use inherit, shared, or private.") from None
            if cmd.identity_name is not None:
                from app.channels.routing.identity_scope import default_identity_id

                bind_kwargs["identity_id"] = default_identity_id(msg.channel, chat_id, msg.thread_id)
                bind_kwargs["identity_name"] = cmd.identity_name
                bind_kwargs["identity_revoked"] = False
            ctx = await topic_resolver.bind_topic(**bind_kwargs)
            if ctx.agent_id and cmd.agent_id and ctx.agent_id != cmd.agent_id:
                agent_label = get_text(
                    msg,
                    "topic_agent_switched",
                    from_agent=cmd.agent_id,
                    to_agent=ctx.agent_id,
                )
            elif ctx.agent_id:
                agent_label = get_text(msg, "topic_agent_only", agent_id=ctx.agent_id)
            else:
                agent_label = ""
            if ctx.project_id:
                workspace_label = get_text(
                    msg,
                    "topic_workspace_only",
                    workspace=f"project:{ctx.project_id}",
                )
            elif ctx.authorized_path:
                workspace_label = get_text(
                    msg,
                    "topic_workspace_only",
                    workspace=ctx.authorized_path,
                )
            else:
                workspace_label = ""
            if ctx.identity_revoked:
                identity_label = get_text(msg, "topic_identity_revoked")
            elif ctx.identity_name:
                identity_label = get_text(msg, "topic_identity_only", name=ctx.identity_name)
            else:
                identity_label = ""
            scope_label = (
                f"{get_text(msg, 'topic_scope_topic')} {msg.thread_id}" if msg.thread_id else get_text(msg, "topic_scope_channel")
            )
            content = get_text(
                msg,
                "topic_bound",
                scope=scope_label,
                agent_label=agent_label,
                workspace_label=workspace_label,
                identity_label=identity_label,
            )

            channel_obj = bus.get_channel(msg.channel)
            pin_msg_id: str | None = None
            if channel_obj:
                pin_msg_id = await channel_obj.send_placeholder(
                    chat_id,
                    content,
                    thread_id=msg.thread_id,
                )

            if not pin_msg_id:
                reply = OutboundMessage(
                    channel=msg.channel,
                    recipient_id=chat_id,
                    content=content,
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
                )
                await bus.publish_outbound(reply)

            if pin_msg_id and channel_obj:
                await channel_obj.pin_message(chat_id, pin_msg_id)

            logger.warning(
                "AgentRouter: /bind %s %s in %s/%s%s",
                "topic" if msg.thread_id else "channel",
                msg.thread_id or "(channel-level)",
                msg.channel,
                chat_id,
                agent_label,
            )

        elif cmd.action == "unbind":
            removed = await topic_resolver.unbind_topic(msg.channel, chat_id, msg.thread_id)
            scope_label = (
                f"{get_text(msg, 'topic_scope_topic')} {msg.thread_id}" if msg.thread_id else get_text(msg, "topic_scope_channel")
            )
            if removed:
                content = get_text(msg, "topic_unbound", scope=scope_label)
            else:
                content = get_text(msg, "topic_no_binding", scope=scope_name)
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await bus.publish_outbound(reply)
            if removed:
                logger.warning(
                    "AgentRouter: /unbind %s %s in %s/%s",
                    "topic" if msg.thread_id else "channel",
                    msg.thread_id or "(channel-level)",
                    msg.channel,
                    chat_id,
                )

        elif cmd.action == "topic":
            topic_ctx = await topic_resolver.resolve_topic(msg.channel, chat_id, msg.thread_id)
            scope_label = (
                f"{get_text(msg, 'topic_scope_topic')} {msg.thread_id}" if msg.thread_id else get_text(msg, "topic_scope_channel")
            )
            if topic_ctx:
                agent_label = (
                    get_text(msg, "topic_status_agent", agent_id=topic_ctx.agent_id)
                    if topic_ctx.agent_id
                    else get_text(msg, "topic_status_agent_default")
                )
                if topic_ctx.project_id:
                    workspace_label = get_text(
                        msg,
                        "topic_status_workspace",
                        workspace=f"project:{topic_ctx.project_id}",
                    )
                elif topic_ctx.authorized_path:
                    workspace_label = get_text(
                        msg,
                        "topic_status_workspace",
                        workspace=topic_ctx.authorized_path,
                    )
                else:
                    workspace_label = get_text(msg, "topic_status_workspace_default")
                bound_label = get_text(msg, "topic_status_bound_at", bound_at=topic_ctx.bound_at) if topic_ctx.bound_at else ""
                if topic_ctx.identity_revoked:
                    identity_label = get_text(msg, "topic_identity_revoked")
                elif topic_ctx.identity_name:
                    identity_label = get_text(msg, "topic_identity_only", name=topic_ctx.identity_name)
                else:
                    identity_label = ""
                status = get_text(
                    msg,
                    ("topic_status_enabled" if topic_ctx.enabled else "topic_status_disabled"),
                )
                content = get_text(
                    msg,
                    "topic_status",
                    scope=scope_label,
                    agent_label=agent_label,
                    workspace_label=workspace_label,
                    identity_label=identity_label,
                    status=status,
                    bound_label=bound_label,
                )
            else:
                content = get_text(msg, "topic_no_binding_defaults", scope=scope_name)
            reply = OutboundMessage(
                channel=msg.channel,
                recipient_id=chat_id,
                content=content,
                user_id=msg.user_id or "",
                thread_id=msg.thread_id,
                reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
            )
            await bus.publish_outbound(reply)

    except ValueError as exc:
        from app.core.channel_bridge.topic_config import (
            is_search_agent_channel_bind_error,
        )

        logger.warning(
            "AgentRouter: %s command %s rejected for %s/%s/%s: %s",
            "topic" if msg.thread_id else "channel",
            cmd.action,
            msg.channel,
            chat_id,
            msg.thread_id,
            exc,
        )
        if is_search_agent_channel_bind_error(exc):
            content = get_text(msg, "topic_search_agent_rejected")
        else:
            content = get_text(
                msg,
                "topic_command_failed",
                scope=scope_name,
                error="internal error",
            )
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)

    except Exception as exc:
        logger.warning(
            "AgentRouter: %s command %s failed for %s/%s/%s: %s",
            "topic" if msg.thread_id else "channel",
            cmd.action,
            msg.channel,
            chat_id,
            msg.thread_id,
            exc,
        )
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content=get_text(
                msg,
                "topic_command_failed",
                scope=scope_name,
                error="internal error",
            ),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
