"""Outbound notification data types.

[INPUT]
- (none — pure data definitions)

[OUTPUT]
- NotifyTarget: Channel + recipient target for outbound delivery.
- NotifyToolConfig: channel_notify_tool configuration.
- NotifyResult: Send attempt result.
- NotifySessionState: Per-session rate-limit state.

[POS]
Data types for agent-initiated outbound channel notifications.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NotifyTarget:
    """A configured notification target (channel + recipient)."""

    channel: str
    recipient_id: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class NotifyToolConfig:
    """Configuration for channel_notify_tool."""

    allowed_targets: tuple[NotifyTarget, ...] = ()
    rate_limit_per_session: int = 10
    max_body_length: int = 4000


@dataclass(frozen=True, slots=True)
class NotifyResult:
    """Result of a notification send attempt."""

    success: bool
    channel: str = ""
    error: str = ""
    message_id: str = ""


@dataclass(slots=True)
class NotifySessionState:
    """Per-session state for rate limiting."""

    send_count: int = 0
    targets_used: list[str] = field(default_factory=list)
