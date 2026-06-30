"""LangChain adapter for agent-initiated outbound channel notifications.

[INPUT]
- .protocols::NotificationSender (POS: outbound notification sender protocol)
- .target_resolver::resolve_notify_target (POS: whitelist target resolution)
- .types::NotifySessionState, NotifyToolConfig (POS: outbound notification data types)
- app.channels.types.messages::MediaAttachment, MediaType, guess_media_type (POS: media types)

[OUTPUT]
- create_channel_notify_tool: Factory for channel_notify_tool BaseTool.

[POS]
Optional LangChain surface for agent-initiated outbound channel notifications.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool
from langchain_core.tools.convert import tool
from pydantic import BaseModel, Field

from .target_resolver import resolve_notify_target
from .types import NotifySessionState, NotifyToolConfig

if TYPE_CHECKING:
    from app.channels.types.messages import MediaAttachment

    from .protocols import NotificationSender


class _NotifyInput(BaseModel):
    channel: str = Field(
        description=(
            "Target channel name (e.g. 'telegram', 'slack'). "
            "If only one target is configured, this can be omitted."
        ),
        default="",
    )
    target: str = Field(
        description=(
            "Optional recipient ID within the channel. "
            "When omitted, uses the default/only configured target for that channel."
        ),
        default="",
    )
    body: str = Field(description="The notification message content to send.")
    attachments: list[str] = Field(
        description=(
            "Optional file attachments to include with the notification. "
            "Each entry is a local file path (e.g. '/myrm/sandbox/report.pdf') "
            "or a URL (e.g. 'https://example.com/image.png'). "
            "Supported types: images, documents, audio, video."
        ),
        default_factory=list,
    )


def _resolve_attachments(raw_paths: list[str]) -> tuple[tuple[MediaAttachment, ...], list[str]]:
    """Convert raw path/URL strings to MediaAttachment objects.

    Returns (resolved_attachments, errors).
    """
    from app.channels.types.messages import MediaAttachment as MA
    from app.channels.types.messages import guess_media_type

    attachments: list[MA] = []
    errors: list[str] = []

    for entry in raw_paths:
        entry = entry.strip()
        if not entry:
            continue

        is_url = entry.startswith(("http://", "https://"))

        if not is_url and not os.path.isfile(entry):
            errors.append(f"File not found: {entry}")
            continue

        filename = os.path.basename(entry) if not is_url else entry.rsplit("/", 1)[-1]
        media_type = guess_media_type(filename)

        attachments.append(
            MA(
                media_type=media_type,
                url=entry if is_url else None,
                path=entry if not is_url else None,
                filename=filename,
            )
        )

    return tuple(attachments), errors


def create_channel_notify_tool(
    sender: NotificationSender,
    config: NotifyToolConfig,
) -> BaseTool:
    """Create channel_notify_tool bound to the given sender and config."""
    session_state = NotifySessionState()

    @tool("channel_notify_tool", args_schema=_NotifyInput)
    async def channel_notify_tool(
        channel: str = "",
        target: str = "",
        body: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        """Send a notification message to a configured external channel.

        Use this tool when:
        - The user asks to be notified on another platform (e.g. "notify me on Telegram when done")
        - You need to send an alert or result to a specific channel
        - Cross-channel delivery is requested (e.g. "send this summary to Slack")
        - You need to send a file/image/document to an external channel

        The tool only works for channels that the user has explicitly configured
        in their agent's notification settings.
        """
        if not body.strip() and not attachments:
            return "Error: notification body and attachments cannot both be empty."

        if not config.allowed_targets:
            return (
                "Error: no notification targets configured for this agent. "
                "The user needs to configure notification channels in the agent settings."
            )

        if session_state.send_count >= config.rate_limit_per_session:
            return (
                f"Error: notification rate limit reached "
                f"({config.rate_limit_per_session} per session). "
                f"Cannot send more notifications in this session."
            )

        if len(body) > config.max_body_length:
            body_truncated = body[: config.max_body_length] + "\n\n[...truncated]"
        else:
            body_truncated = body

        resolved_target = resolve_notify_target(channel, target, config.allowed_targets)
        if resolved_target is None:
            available = ", ".join(
                f"{entry.channel}:{entry.recipient_id}" + (f" ({entry.label})" if entry.label else "")
                for entry in config.allowed_targets
            )
            return f"Error: target not found or not allowed. Available targets: [{available}]"

        media: tuple[MediaAttachment, ...] = ()
        if attachments:
            media, resolve_errors = _resolve_attachments(attachments)
            if resolve_errors:
                return "Error resolving attachments: " + "; ".join(resolve_errors)

        result = await sender.send(resolved_target, body_truncated, media=media)

        session_state.send_count += 1
        session_state.targets_used.append(f"{resolved_target.channel}:{resolved_target.recipient_id}")

        if result.success:
            label = resolved_target.label or resolved_target.recipient_id
            media_note = f" with {len(media)} attachment(s)" if media else ""
            return f"Notification sent successfully to {resolved_target.channel} ({label}){media_note}."
        return f"Error: failed to send notification — {result.error}"

    return channel_notify_tool
