"""LangChain adapter for agent-initiated outbound channel notifications.

[INPUT]
- .protocols::NotificationSender (POS: outbound notification sender protocol)
- .target_resolver::resolve_notify_target (POS: whitelist target resolution)
- .types::NotifySessionState, NotifyToolConfig (POS: outbound notification data types)

[OUTPUT]
- create_channel_notify_tool: Factory for channel_notify_tool BaseTool.

[POS]
Optional LangChain surface for agent-initiated outbound channel notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool
from langchain_core.tools.convert import tool
from pydantic import BaseModel, Field

from .target_resolver import resolve_notify_target
from .types import NotifySessionState, NotifyToolConfig

if TYPE_CHECKING:
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
    ) -> str:
        """Send a notification message to a configured external channel.

        Use this tool when:
        - The user asks to be notified on another platform (e.g. "notify me on Telegram when done")
        - You need to send an alert or result to a specific channel
        - Cross-channel delivery is requested (e.g. "send this summary to Slack")

        The tool only works for channels that the user has explicitly configured
        in their agent's notification settings.
        """
        if not body.strip():
            return "Error: notification body cannot be empty."

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

        result = await sender.send(resolved_target, body_truncated)

        session_state.send_count += 1
        session_state.targets_used.append(f"{resolved_target.channel}:{resolved_target.recipient_id}")

        if result.success:
            label = resolved_target.label or resolved_target.recipient_id
            return f"Notification sent successfully to {resolved_target.channel} ({label})."
        return f"Error: failed to send notification — {result.error}"

    return channel_notify_tool
