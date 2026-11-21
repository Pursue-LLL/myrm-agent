"""Outbound notification data types.

[INPUT]
- (none — pure data definitions)

[OUTPUT]
- NotifyTarget: Channel + recipient target for outbound delivery.
- NotifyToolConfig: channel_notify_tool configuration (closed destination set, limits).
- NotifyResult: Send attempt result.
- NotifySessionState: Per-session rate-limit state.

[POS]
Data types for agent-initiated outbound channel notifications.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotifyTarget:
    """A configured notification target (channel + recipient)."""

    channel: str
    recipient_id: str
    label: str = ""


@dataclass(frozen=True, slots=True)
class NotifyToolConfig:
    """Configuration for channel_notify_tool.

    ``destinations`` is the closed set the model can choose from: the name it passes as ``destination``
    mapped to the target that name delivers to, in the order the user configured them.
    """

    destinations: Mapping[str, NotifyTarget]
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
    """Per-session state for rate limiting.

    ``send_count`` counts the sends a session has claimed: a slot is taken before delivery, so failed sends count too.
    """

    send_count: int = 0
