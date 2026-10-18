"""Channel status, health, diagnostics and capability types.

[INPUT]
(No external dependencies, pure data type definitions)

[OUTPUT]
- ChannelStatus, StartMode, ChannelHealth: Channel status, startup strategy, and health
- ChannelActivity, ChannelIssue: Activity and issue diagnostics
- ChannelCapabilities: Channel capability declaration
- GroupInfo, TopicContext: Group and topic context

[POS]
Channel status and diagnostic type definitions. Used for Gateway health checks,
issue collection, and capability negotiation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum


class ChannelStatus(StrEnum):
    """Runtime status of a channel instance."""

    IDLE = "idle"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"
    STOPPED = "stopped"
    DISABLED = "disabled"


class StartMode(StrEnum):
    """Channel startup strategy used by ChannelGateway.

    AUTO: Gateway calls start() immediately during gateway.start().
    ON_DEMAND: Gateway skips start(); channel is started explicitly
        when the user triggers login or when a persisted session exists.
    """

    AUTO = "auto"
    ON_DEMAND = "on_demand"


class ReactionLevel(StrEnum):
    """Controls which automatic reactions the router emits on inbound messages.

    - off: No reactions at all (for formal enterprise environments).
    - simple: React  on success,  on failure.
    - full: Lifecycle reactions —  on receive, then / on completion
            ( is automatically removed).
    """

    OFF = "off"
    SIMPLE = "simple"
    FULL = "full"


_CIRCUIT_BREAKER_THRESHOLD = 5
_CIRCUIT_BREAKER_COOLDOWN = 30.0


@dataclass
class ChannelHealth:
    """Mutable health metrics for a channel instance.

    Updated by ``BaseChannel.health_check()`` and consumed by
    ``ChannelGateway._health_loop`` for backoff decisions.

    Circuit breaker: after ``_CIRCUIT_BREAKER_THRESHOLD`` consecutive
    send failures, outbound dispatch is paused for ``_CIRCUIT_BREAKER_COOLDOWN``
    seconds to avoid flooding a degraded API.
    """

    consecutive_failures: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_error: str = ""
    circuit_open_until: float = 0.0

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_success_at = time.monotonic()
        self.last_error = ""
        self.circuit_open_until = 0.0

    def record_failure(self, error: str = "") -> None:
        self.consecutive_failures += 1
        self.last_failure_at = time.monotonic()
        self.last_error = error
        if self.consecutive_failures >= _CIRCUIT_BREAKER_THRESHOLD:
            self.circuit_open_until = time.monotonic() + _CIRCUIT_BREAKER_COOLDOWN

    @property
    def circuit_open(self) -> bool:
        """True if the circuit breaker is tripped (outbound should be paused)."""
        return self.circuit_open_until > time.monotonic()


@dataclass
class ChannelActivity:
    """Per-channel inbound/outbound activity.

    Tracked by Router (inbound) and MessageBus (outbound) and surfaced by the
    status API, which reports when a channel last saw traffic in either
    direction and how many outbound attempts failed.
    """

    last_inbound_at: float | None = None
    last_outbound_at: float | None = None
    total_outbound: int = 0
    total_errors: int = 0

    def record_inbound(self) -> None:
        self.last_inbound_at = time.time()

    def record_outbound(self) -> None:
        self.last_outbound_at = time.time()
        self.total_outbound += 1

    def record_error(self) -> None:
        self.total_errors += 1

    @property
    def last_active_at(self) -> float | None:
        """Most recent activity across both directions."""
        if self.last_inbound_at and self.last_outbound_at:
            return max(self.last_inbound_at, self.last_outbound_at)
        return self.last_inbound_at or self.last_outbound_at


class IssueSeverity(StrEnum):
    """Severity level for a channel status issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueKind(StrEnum):
    """Category of a channel status issue."""

    AUTH = "auth"
    CONFIG = "config"
    DEPENDENCY = "dependency"
    PERMISSIONS = "permissions"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class ChannelIssue:
    """Structured diagnostic issue for a channel.

    Collected by ``BaseChannel.collect_issues()`` and aggregated by
    ``ChannelGateway.collect_all_issues()`` for the status API.
    """

    kind: IssueKind
    severity: IssueSeverity
    message: str
    fix: str = ""


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    """Declares what a channel supports (used by Router for format decisions).

    Content flags:
    - ``text``, ``markdown``, ``media``: basic content types
    - ``voice_message``: inbound/outbound voice notes
    - ``file_upload``: arbitrary file attachment support

    Interactive component flags:
    - ``buttons``: native ActionButton rendering (Telegram InlineKeyboard, etc.)
    - ``quick_replies``: native QuickReply rendering (WhatsApp quick-replies, etc.)
    - ``select_menus``: native SelectMenu rendering (Discord StringSelect, etc.)

    Mutation flags (used by Router to decide streaming strategy):
    - ``edit``: channel implements edit_message
    - ``delete``: channel implements delete_message
    - ``reactions``: channel implements react_to_message
    - ``typing_indicator``: channel supports start_typing / stop_typing
    - ``typing_keepalive_interval``: seconds between periodic typing refreshes
      (0 = no keepalive; platforms like WeChat auto-dismiss after ~5 s)

    Delivery flag:
    - ``message_ids``: ``send()`` returns the platform message id on success.
      Channels whose send API returns no id (DingTalk, IRC, WeCom, ...) declare
      ``False`` so that a ``None`` result counts as delivered; failures on such
      channels must raise instead of returning ``None``.
    """

    text: bool = True
    markdown: bool = False
    media: bool = False
    voice_message: bool = False
    file_upload: bool = False
    buttons: bool = False
    quick_replies: bool = False
    select_menus: bool = False
    threads: bool = False
    edit: bool = False
    delete: bool = False
    reactions: bool = False
    typing_indicator: bool = True
    typing_keepalive_interval: float = 0.0
    max_text_length: int = 4000
    send_rate_limit: float = 0.0
    message_ids: bool = True


@dataclass(frozen=True, slots=True)
class GroupInfo:
    """Metadata for a discovered group chat.

    Returned by BaseChannel.list_groups() for group discovery/registration UI.
    """

    jid: str
    name: str
    channel: str = ""
    is_enabled: bool = False
