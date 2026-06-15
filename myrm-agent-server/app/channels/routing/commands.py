"""Command parsing and slash-command execution for IM channels.

Argument parsers for complex commands (approval, yolo, personality, topic)
and high-level async handlers for topic management, chat compaction,
and turn management (retry/undo) that can be delegated from AgentRouter
without bloating the core routing loop.

[INPUT]
- channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.core.bus::MessageBus (POS: async message bus)
- channels.protocols.compact::CompactHandler (POS: /compact business-layer handling protocol)
- channels.protocols.turn_management::RetryHandler, UndoHandler (POS: /retry, /undo protocols)
- channels.protocols.topic::TopicManager (POS: topic management protocol)
- channels.routing.policy_resolver::PolicyResolver (POS: DM/group policy resolution + identity resolution)
- channels.routing.router_keys::routing_session_key (POS: /new session marker and mapping key format)

[OUTPUT]
- parse_approval_command, is_explicit_approval_command: approval command parsing
- parse_yolo_args, parse_personality_args, parse_memory_args: argument parsers for complex commands
- MemoryAction: Literal type for /memory sub-commands
- TopicCommand, parse_topic_args: topic command parsing
- handle_new_session, handle_compact, handle_topic_command: async command handlers
- handle_retry, handle_undo: async command handlers

[POS]
Slash command argument parsing and handling module: pure-function parsers and
higher-order async handlers; parsers are I/O-free, handlers receive
dependencies via parameter injection.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import time
from typing import TYPE_CHECKING, Literal, get_args

from app.channels.i18n import get_text
from app.channels.routing.router_keys import routing_session_key
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
)

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.protocols.compact import CompactHandler
    from app.channels.protocols.topic import TopicManager
    from app.channels.protocols.turn_management import (
        RetryHandler,
        UndoHandler,
    )
    from app.channels.routing.policy_resolver import (
        PolicyResolver,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parsers for complex commands
# ---------------------------------------------------------------------------


def parse_yolo_args(raw_args: str) -> tuple[str, int | None] | None:
    """Parse YOLO mode arguments.

    Supported formats:
    - ""              -> ("toggle", None)
    - "toggle"        -> ("toggle", None)
    - "on"            -> ("on", None)
    - "on 3600"       -> ("on", 3600)
    - "off"           -> ("off", None)
    - "status"        -> ("status", None)

    Returns:
        Tuple of (action, timeout_seconds) or None if invalid.
    """
    parts = raw_args.strip().lower().split()
    if not parts:
        return ("toggle", None)
    if len(parts) == 1:
        action = parts[0]
        if action in ("on", "off", "toggle", "status"):
            return (action, None)
        return None
    if len(parts) == 2 and parts[0] == "on":
        try:
            timeout = int(parts[1])
            if timeout <= 0:
                return None
            return ("on", timeout)
        except ValueError:
            return None
    return None


def parse_personality_args(raw_args: str) -> str:
    """Parse personality command arguments.

    Returns:
        Style name or "list" if no argument given.
    """
    style = raw_args.strip().lower()
    return style if style else "list"


MemoryAction = Literal["pending", "approve", "reject", "approve_all"]


def parse_memory_args(raw_args: str) -> tuple[MemoryAction, str | None]:
    """Parse /memory sub-command arguments.

    Supported formats:
    - ""                    -> ("pending", None)
    - "pending"             -> ("pending", None)
    - "approve <id>"        -> ("approve", "<id>")
    - "reject <id>"         -> ("reject", "<id>")
    - "approve all"         -> ("approve_all", None)

    Returns:
        Tuple of (action, memory_id_or_none).
    """
    parts = raw_args.strip().split(maxsplit=1)
    if not parts:
        return ("pending", None)

    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action == "pending":
        return ("pending", None)

    if action == "approve":
        if rest.lower() == "all":
            return ("approve_all", None)
        return ("approve", rest) if rest else ("pending", None)

    if action == "reject":
        return ("reject", rest) if rest else ("pending", None)

    return ("pending", None)


# ---------------------------------------------------------------------------
# Approval decision model
# ---------------------------------------------------------------------------
#
# Three-tier decision aligning with langgraph interrupt() resume semantics and
# harness `_batch_decisions` allow-always allowlist support:
#   - allow_once   : approve current invocation only
#   - allow_always : approve and persist into the user's allowlist (skip future ASK)
#   - deny         : reject current invocation
#
# Reaction emoji mapping (after Unicode normalization):
#   👍 / ❤ / ✅ / 🤝 / 💪    -> allow_once
#   ♾ / ⭐                    -> allow_always
#   👎 / ❌ / 🚫               -> deny
#
# Slash commands & natural shortcuts mirror the three tiers:
#   /approve, 1, y, yes, ok, 同意, 可以, 没问题, 好的, 是 -> allow_once
#   /approve-always, /always, !y, 1!, 永远允许, 总是允许    -> allow_always
#   /deny, 2, n, no, d, deny, r, reject, 拒绝, 不行, 不需要 -> deny
#
# Batch tokens ('/batch a,aa,d'):
#   a / approve            -> allow_once
#   aa / always            -> allow_always
#   d / deny / r / reject  -> deny

ApprovalDecision = Literal["allow_once", "allow_always", "deny"]
_APPROVAL_DECISION_VALUES: frozenset[str] = frozenset(get_args(ApprovalDecision))


_VARIATION_SELECTOR_RE = re.compile(r"[\uFE0E\uFE0F]")
_FITZPATRICK_RE = re.compile(r"[\U0001F3FB-\U0001F3FF]")

_APPROVE_ONCE_EMOJIS: frozenset[str] = frozenset({"\U0001f44d", "\u2764", "\u2705", "\U0001f91d", "\U0001f4aa"})
_APPROVE_ALWAYS_EMOJIS: frozenset[str] = frozenset({"\u267e", "\u2b50"})
_DENY_EMOJIS: frozenset[str] = frozenset({"\U0001f44e", "\u274c", "\U0001f6ab"})

_APPROVE_ONCE_TEXT: frozenset[str] = frozenset(
    {
        "/approve",
        "1",
        "y",
        "yes",
        "a",
        "approve",
        "ok",
        "same",
        "'s",
        "没问题",
        "可以",
        "是",
        "同意",
        "好的",
    }
)
_APPROVE_ALWAYS_TEXT: frozenset[str] = frozenset(
    {
        "/approve-always",
        "/always",
        "!y",
        "1!",
        "aa",
        "永远允许",
        "总是允许",
        "一直允许",
    }
)
_DENY_TEXT: frozenset[str] = frozenset(
    {
        "/deny",
        "2",
        "n",
        "no",
        "d",
        "deny",
        "r",
        "reject",
        "拒绝",
        "不行",
        "不需要",
    }
)


def normalize_approval_emoji(value: str) -> str:
    """Strip variation selectors (FE0E/FE0F) and Fitzpatrick skin-tone modifiers.

    Ensures '👍' and '👍🏼' and '👍️' all collapse to the same key so emoji matching
    is reaction-source agnostic. Whitespace is also trimmed.
    """
    cleaned = _VARIATION_SELECTOR_RE.sub("", value.strip())
    return _FITZPATRICK_RE.sub("", cleaned)


def parse_approval_command(content: str) -> ApprovalDecision | list[ApprovalDecision] | None:
    """Parse approval commands into the three-tier decision model.

    Supports slash commands (/approve, /approve-always, /deny), natural shortcuts
    (1, 2, y, n, ok, etc.), emoji reactions (👍/♾/👎 with skin-tone & VS-16 normalisation),
    and batch mode (/batch a,aa,d).

    Returns:
        - ``"allow_once" | "allow_always" | "deny"`` for a single decision
        - ``list[ApprovalDecision]`` for batch decisions
        - ``None`` if not an approval command
    """
    cmd = content.strip()

    normalized = normalize_approval_emoji(cmd)
    if normalized in _APPROVE_ALWAYS_EMOJIS:
        return "allow_always"
    if normalized in _APPROVE_ONCE_EMOJIS:
        return "allow_once"
    if normalized in _DENY_EMOJIS:
        return "deny"

    cmd_lower = cmd.lower()

    if cmd_lower in _APPROVE_ALWAYS_TEXT:
        return "allow_always"
    if cmd_lower in _APPROVE_ONCE_TEXT:
        return "allow_once"
    if cmd_lower in _DENY_TEXT:
        return "deny"

    if cmd_lower.startswith("/batch "):
        batch_spec = cmd_lower[7:].strip()
        if not batch_spec:
            return None

        decisions: list[ApprovalDecision] = []
        for raw_token in batch_spec.split(","):
            token = raw_token.strip()
            if token in ("a", "approve"):
                decisions.append("allow_once")
            elif token in ("aa", "always", "approve-always"):
                decisions.append("allow_always")
            elif token in ("d", "deny", "r", "reject"):
                decisions.append("deny")
            else:
                return None

        return decisions if decisions else None

    return None


def is_explicit_approval_command(content: str) -> bool:
    """Whether ``content`` is an explicit /approve, /approve-always, /deny, or /batch."""
    cmd = content.strip().lower()
    return cmd in ("/approve", "/approve-always", "/always", "/deny") or cmd.startswith("/batch ")


@dataclasses.dataclass(frozen=True, slots=True)
class TopicCommand:
    """Parsed topic management command."""

    action: Literal["bind", "unbind", "topic"]
    agent_id: str | None = None


def parse_topic_args(action: str, raw_args: str) -> TopicCommand:
    """Parse topic command arguments from resolved command.

    Args:
        action: The topic action ("bind", "unbind", "topic").
        raw_args: Trailing arguments from the resolved command.
    """
    agent_id = raw_args.strip() if raw_args.strip() and action == "bind" else None
    return TopicCommand(action=action, agent_id=agent_id)


# ---------------------------------------------------------------------------
# Delegated command handlers (called by AgentRouter)
# ---------------------------------------------------------------------------


async def handle_new_session(
    msg: InboundMessage,
    bus: MessageBus,
    new_session_peers: dict[str, float],
) -> None:
    """Handle /new command: mark peer so next message creates a fresh Chat."""
    peer_key = routing_session_key(msg.channel, msg.chat_id or msg.sender_id)
    new_session_peers[peer_key] = time.monotonic()

    chat_id = msg.chat_id or msg.sender_id
    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=chat_id,
        content=get_text(msg, "new_session_started"),
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=msg.message_id if msg.is_group else None,
    )
    await bus.publish_outbound(reply)


async def handle_compact(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    compact_handler: CompactHandler | None = None,
    *,
    focus_topic: str = "",
) -> None:
    """Handle /compact command: compress chat context to reduce token cost.

    When compact_handler is None, replies with "Compaction not configured."
    Business layer provides CompactHandler to perform DB/chat/compact operations.
    """
    from app.channels.protocols.compact import (
        MAX_FOCUS_TOPIC_LENGTH,
    )

    peer_id = msg.chat_id or msg.sender_id
    effective_topic = focus_topic[:MAX_FOCUS_TOPIC_LENGTH].strip() if focus_topic else ""

    if not compact_handler:
        content = get_text(msg, "compact_not_configured")
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=content,
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return

    try:
        if msg.is_group:
            resolved = await resolver.resolve_group_user(msg)
            if not resolved:
                return
            user_id, resolved_msg = resolved
            msg = resolved_msg
        else:
            dm_uid = await resolver.resolve_dm_user(msg)
            if not dm_uid:
                return
            user_id = dm_uid

        result = await compact_handler(msg, user_id, focus_topic=effective_topic)

        if result.compacted:
            topic_hint = f" (focus: {effective_topic})" if effective_topic else ""
            content = get_text(
                msg,
                "compact_success",
                message_count=result.message_count,
                tokens_saved=result.tokens_saved,
                topic_hint=topic_hint,
            )
        else:
            content = get_text(msg, "compact_skipped", reason=result.reason or "no action needed")
    except Exception as exc:
        logger.warning("AgentRouter: /compact failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "compact_failed", error=str(exc))

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)


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
            ctx = await topic_resolver.bind_topic(msg.channel, chat_id, msg.thread_id, agent_id=cmd.agent_id)
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
            scope_label = (
                f"{get_text(msg, 'topic_scope_topic')} {msg.thread_id}" if msg.thread_id else get_text(msg, "topic_scope_channel")
            )
            content = get_text(
                msg,
                "topic_bound",
                scope=scope_label,
                agent_label=agent_label,
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
                bound_label = get_text(msg, "topic_status_bound_at", bound_at=topic_ctx.bound_at) if topic_ctx.bound_at else ""
                status = get_text(
                    msg,
                    ("topic_status_enabled" if topic_ctx.enabled else "topic_status_disabled"),
                )
                content = get_text(
                    msg,
                    "topic_status",
                    scope=scope_label,
                    agent_label=agent_label,
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
                error=str(exc),
            ),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)


async def handle_retry(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    retry_handler: RetryHandler | None = None,
) -> InboundMessage | None:
    """Handle /retry command: delete last assistant turn and return original query for re-execution.

    Returns an InboundMessage with the original query if retry succeeded (router should
    re-dispatch), or None if no re-execution is needed.
    """
    peer_id = msg.chat_id or msg.sender_id

    if not retry_handler:
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=get_text(msg, "retry_not_configured"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return None

    try:
        if msg.is_group:
            resolved = await resolver.resolve_group_user(msg)
            if not resolved:
                return None
            user_id, resolved_msg = resolved
            msg = resolved_msg
        else:
            dm_uid = await resolver.resolve_dm_user(msg)
            if not dm_uid:
                return None
            user_id = dm_uid

        result = await retry_handler(msg, user_id)

        if result.success and result.query:
            return dataclasses.replace(msg, content=result.query)

        if result.deleted_count == 0:
            content = get_text(msg, "retry_nothing")
        else:
            content = get_text(msg, "retry_failed")
    except Exception as exc:
        logger.warning("AgentRouter: /retry failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "retry_failed_error", error=str(exc))

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)
    return None


async def handle_undo(
    msg: InboundMessage,
    bus: MessageBus,
    resolver: PolicyResolver,
    undo_handler: UndoHandler | None = None,
) -> None:
    """Handle /undo command: delete the entire last turn (user + assistant messages)."""
    peer_id = msg.chat_id or msg.sender_id

    if not undo_handler:
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=peer_id,
            content=get_text(msg, "undo_not_configured"),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await bus.publish_outbound(reply)
        return

    try:
        if msg.is_group:
            resolved = await resolver.resolve_group_user(msg)
            if not resolved:
                return
            user_id, resolved_msg = resolved
            msg = resolved_msg
        else:
            dm_uid = await resolver.resolve_dm_user(msg)
            if not dm_uid:
                return
            user_id = dm_uid

        result = await undo_handler(msg, user_id)

        if result.success:
            if result.deleted_count > 0:
                content = get_text(msg, "undo_success", count=result.deleted_count)
            else:
                content = get_text(msg, "undo_nothing")
        else:
            content = get_text(msg, "undo_failed")
    except Exception as exc:
        logger.warning("AgentRouter: /undo failed for %s/%s: %s", msg.channel, peer_id, exc)
        content = get_text(msg, "undo_failed_error", error=str(exc))

    reply = OutboundMessage(
        channel=msg.channel,
        recipient_id=peer_id,
        content=content,
        user_id=msg.user_id or "",
        thread_id=msg.thread_id,
        reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
    )
    await bus.publish_outbound(reply)
