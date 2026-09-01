"""Adaptive Card Formatter for cross-channel structured notifications.

Transforms AppEvents into rich OutboundMessage payloads containing structured
Markdown content, indicator headers, and interactive ActionButtons/QuickReplies.

[INPUT]
- app.services.event.app_event_bus::AppEvent, AppEventType
- app.channels.types.components::ActionButton, ButtonStyle, QuickReply, ComponentRow
- app.channels.types.messages::OutboundMessage

[OUTPUT]
- FormattedNotification: dataclass with content, components, quick_replies, metadata
- format_notification(event: AppEvent) -> FormattedNotification | None
- format_legacy_text(event: AppEvent) -> str | None
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.channels.types.components import (
    ActionButton,
    ButtonStyle,
    ComponentRow,
    QuickReply,
)
from app.services.event.app_event_bus import AppEvent, AppEventType

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FormattedNotification:
    """Structured notification ready to be converted into an OutboundMessage."""

    content: str
    components: tuple[ComponentRow, ...] = ()
    quick_replies: tuple[QuickReply, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


_EVENT_TEMPLATES: dict[AppEventType, str] = {
    AppEventType.PAIRING_PENDING: (
        "[Myrm AI] New pairing request: {channel} / {sender_id}\nPlease go to Settings → Channels to approve or block."
    ),
    AppEventType.APPROVAL_REQUIRED: (
        "[Myrm AI] Approval required: {action_type} (severity: {severity})\nPlease check the app to approve or reject."
    ),
    AppEventType.HEALTH_ALERT: "[Myrm AI] Health alert ({component}): {message}",
    AppEventType.BUDGET_ALERT: "[Myrm AI] Budget alert: {status} — {pct}% used (${today_cost} / ${daily_limit})",
    AppEventType.NEW_SKILL_DRAFT: "[Myrm AI] New skill draft '{name}' ({draft_type}) needs your review.",
    AppEventType.MESSAGE_DEAD_LETTERED: "[Myrm AI] Message delivery failed on {channel}: {error_reason}",
    AppEventType.CHANNEL_DISCONNECTED: (
        "[Myrm AI] Channel '{channel}' disconnected (status: {status}).\nPlease check Settings → Channels."
    ),
    AppEventType.WECHAT_SESSION_EXPIRED: "[Myrm AI] WeChat session expired. Please re-login in Settings → Channels.",
    AppEventType.CONFIG_HEALTH_WARNING: "[Myrm AI] Configuration issue detected.\nMissing: {missing_items}",
    AppEventType.SYSTEM_NOTIFICATION: "[Myrm AI] {title}: {message}",
    AppEventType.GOAL_TERMINAL: (
        "[Myrm AI] Goal {status}: {objective}\n"
        "{files_modified} files · {turns_used} turns · {execution_duration_s:.0f}s · {total_tokens:,} tokens · ${total_cost_usd:.2f}"
    ),
    AppEventType.SUBAGENT_STALE: (
        "[Myrm AI] Subagent stalled: {agent_type} ({task_id})\nNo progress for {stale_duration_seconds:.0f}s · {wasted_tokens:,} tokens"
    ),
    AppEventType.GOAL_DEQUEUED: "[Myrm AI] Next goal started: {objective}",
    AppEventType.SESSION_COMPLETED: "[Myrm AI] Session completed: {title}",
    AppEventType.SESSION_FAILED: "[Myrm AI] Session failed: {title}",
    AppEventType.OAUTH_REAUTH_REQUIRED: (
        "[Myrm AI] {issuer} authorization expired ({reason}).\nPlease go to Settings → Integrations to reauthorize."
    ),
}

_KANBAN_TERMINAL_ACTIONS = frozenset(
    {
        "task_completed",
        "task_blocked",
        "task_failed",
    }
)
_KANBAN_TERMINAL_STATUSES = frozenset(
    {
        "completed",
        "blocked",
        "failed",
    }
)


def format_legacy_text(event: AppEvent) -> str | None:
    """Format an AppEvent into legacy single-line text for backwards compatibility."""
    if event.event_type == AppEventType.KANBAN_TASK_UPDATED:
        return _format_kanban_text(event.data)

    template = _EVENT_TEMPLATES.get(event.event_type)
    if not template:
        return None
    try:
        return template.format(**event.data)
    except (KeyError, ValueError) as exc:
        logger.warning("Failed to format legacy notification for %s: %s", event.event_type, exc)
        return None


def _format_kanban_text(data: dict[str, Any]) -> str | None:
    action = str(data.get("action", ""))
    status = str(data.get("status", ""))

    if action == "moved":
        if status not in _KANBAN_TERMINAL_STATUSES:
            return None
    elif action not in _KANBAN_TERMINAL_ACTIONS:
        return None

    title = str(data.get("title", data.get("task_id", "?")))
    detail = str(data.get("detail", ""))
    suffix = f"\n{detail[:200]}" if detail else ""

    resolved_status = status or action.removeprefix("task_")
    if resolved_status == "completed":
        return f'[Myrm AI] Kanban task "{title}" completed{suffix}'
    if resolved_status == "blocked":
        return f'[Myrm AI] Kanban task "{title}" blocked{suffix}'
    if resolved_status == "failed":
        return f'[Myrm AI] Kanban task "{title}" failed{suffix}'
    return None


def _format_approval_required(data: dict[str, Any]) -> FormattedNotification | None:
    approval_id = str(data.get("approval_id", ""))
    action_type = str(data.get("action_type", "action"))
    severity = str(data.get("severity", "medium"))
    description = str(data.get("description", ""))

    title = f"⚠️ **Approval Required: {action_type}**"
    severity_note = f"Severity: `{severity}`"
    content = f"{title}\n{severity_note}"
    if description:
        content += f"\n\n> {description}"

    components: tuple[ComponentRow, ...] = ()
    if approval_id:
        approve_btn = ActionButton(
            label="Approve",
            action_id=f"approval:approve:{approval_id}",
            style=ButtonStyle.PRIMARY,
        )
        reject_btn = ActionButton(
            label="Reject",
            action_id=f"approval:reject:{approval_id}",
            style=ButtonStyle.DANGER,
        )
        components = ((approve_btn, reject_btn),)

    return FormattedNotification(
        content=content,
        components=components,
        metadata={"approval_id": approval_id, "severity": severity},
    )


def _format_pairing_pending(data: dict[str, Any]) -> FormattedNotification:
    channel = str(data.get("channel", "unknown"))
    sender_id = str(data.get("sender_id", "unknown"))

    content = (
        f"🔐 **New Pairing Request**\n\n"
        f"• **Channel**: `{channel}`\n"
        f"• **Sender**: `{sender_id}`\n\n"
        f"Please approve or block this contact in Settings → Channels."
    )

    approve_btn = ActionButton(
        label="Approve",
        action_id=f"pairing:approve:{channel}:{sender_id}",
        style=ButtonStyle.PRIMARY,
    )
    block_btn = ActionButton(
        label="Block",
        action_id=f"pairing:block:{channel}:{sender_id}",
        style=ButtonStyle.DANGER,
    )
    return FormattedNotification(
        content=content,
        components=((approve_btn, block_btn),),
        metadata={"channel": channel, "sender_id": sender_id},
    )


def _format_goal_terminal(data: dict[str, Any]) -> FormattedNotification | None:
    status = str(data.get("status", ""))
    objective = str(data.get("objective", ""))
    if not status or not objective:
        return None

    try:
        files_modified = int(data.get("files_modified", 0))
        turns_used = int(data.get("turns_used", 0))
        duration_s = float(data.get("execution_duration_s", 0.0))
        total_tokens = int(data.get("total_tokens", 0))
        total_cost_usd = float(data.get("total_cost_usd", 0.0))
    except (TypeError, ValueError):
        return None

    icon = "✅" if status in ("complete", "completed") else ("🛑" if status == "cancelled" else "⚠️")
    title = f"{icon} **Goal {status.capitalize()}**"

    lines = [
        title,
        f"**Objective**: {objective}",
        "",
        f"📊 **Metrics**: {files_modified} files · {turns_used} turns · {duration_s:.0f}s · {total_tokens:,} tokens · ${total_cost_usd:.2f}",
    ]

    session_id = data.get("session_id")
    components: tuple[ComponentRow, ...] = ()
    if session_id:
        view_btn = ActionButton(
            label="View Session",
            action_id=f"session:view:{session_id}",
            style=ButtonStyle.PRIMARY,
        )
        components = ((view_btn,),)

    return FormattedNotification(
        content="\n".join(lines),
        components=components,
        metadata={
            "status": status,
            "session_id": str(session_id) if session_id else "",
            "cost_usd": total_cost_usd,
            "duration_s": duration_s,
        },
    )


def _format_background_task_done(data: dict[str, Any]) -> FormattedNotification | None:
    task_id = str(data.get("task_id", ""))
    status = str(data.get("status", "completed"))
    title = str(data.get("title", data.get("task_title", "Task")))
    summary = str(data.get("summary", data.get("detail", "")))

    icon = "✅" if status in ("completed", "complete") else ("🛑" if status == "failed" else "⚠️")
    header = f"{icon} **Task {status.capitalize()}: {title}**"

    lines = [header]
    if summary:
        lines.append(f"\n{summary}")

    components: tuple[ComponentRow, ...] = ()
    board_id = data.get("board_id")
    if board_id:
        view_btn = ActionButton(
            label="View Kanban",
            action_id=f"kanban:view:{board_id}",
            style=ButtonStyle.DEFAULT,
        )
        components = ((view_btn,),)

    return FormattedNotification(
        content="\n".join(lines),
        components=components,
        metadata={
            "task_id": task_id,
            "status": status,
            "board_id": str(board_id) if board_id else "",
        },
    )


def format_notification(event: AppEvent) -> FormattedNotification | None:
    """Transform an AppEvent into a rich FormattedNotification.

    Returns None for events that should not trigger IM push notifications.
    """
    if event.event_type == AppEventType.APPROVAL_REQUIRED:
        return _format_approval_required(event.data)
    elif event.event_type == AppEventType.PAIRING_PENDING:
        return _format_pairing_pending(event.data)
    elif event.event_type == AppEventType.GOAL_TERMINAL:
        return _format_goal_terminal(event.data)
    elif event.event_type == AppEventType.BACKGROUND_TASK_DONE:
        return _format_background_task_done(event.data)
    elif event.event_type in (
        AppEventType.SESSION_COMPLETED,
        AppEventType.SESSION_FAILED,
    ):
        status = "completed" if event.event_type == AppEventType.SESSION_COMPLETED else "failed"
        title = str(event.data.get("title", "Session"))
        icon = "✅" if status == "completed" else "🛑"
        content = f"{icon} **Session {status.capitalize()}: {title}**"
        detail = event.data.get("detail") or event.data.get("error")
        if detail:
            content += f"\n\n{detail}"
        session_id = event.data.get("session_id") or event.data.get("chat_id")
        components: tuple[ComponentRow, ...] = ()
        if session_id:
            view_btn = ActionButton(
                label="Open Session",
                action_id=f"session:view:{session_id}",
                style=ButtonStyle.PRIMARY,
            )
            components = ((view_btn,),)
        return FormattedNotification(
            content=content,
            components=components,
            metadata={
                "session_id": str(session_id) if session_id else "",
                "status": status,
            },
        )
    elif event.event_type == AppEventType.KANBAN_TASK_UPDATED:
        text = _format_kanban_text(event.data)
        if not text:
            return None
        return FormattedNotification(content=text, metadata=dict(event.data))

    # Generic fallback using legacy template formatting
    text = format_legacy_text(event)
    if not text:
        return None
    return FormattedNotification(content=text, metadata=dict(event.data))
