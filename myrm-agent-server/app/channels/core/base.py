"""Abstract base class for all channel providers.

Every channel (Chat, Telegram, Feishu, Webhook, …) implements this
interface so the Gateway can manage them uniformly.


[INPUT]
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.reliability.retry::RetryConfig, send_with_retry (POS: async retry utility with exponential backoff)
- channels.core.credentials::ChannelCredentialSpec (POS: framework-level credential type definition)
- channels.core.inbound_pipeline::InboundPipelineMixin (POS: inbound filter, dedup, rate limit, access check, debounce, dispatch)
- channels.core.reply_shortcuts::ReplyShortcutsMixin (POS: ``respond`` / ``broadcast`` on top of ``send``)
- channels.core.provider_hooks::ProviderHooksMixin (POS: optional hooks: routes, async login, OAuth2 callback, history, context document)

[OUTPUT]
- BaseChannel: abstract base class defining channel lifecycle and message send/receive interface; the inbound pipeline, the reply shortcuts and the optional provider hooks come from its mixins

[POS]
Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly.
Supports outbound (send) and inbound (on_inbound callback) bidirectional communication.
Providers may declare credential_spec and from_credentials for self-contained credential management.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import TYPE_CHECKING, ClassVar, Self

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.allow_policy import (
    SELECTIVE_POLICY,
    AllowPolicy,
)
from app.channels.core.events import EventEmitter
from app.channels.core.inbound_pipeline import InboundHandler, InboundPipelineMixin, SenderGate
from app.channels.core.provider_hooks import ProviderHooksMixin
from app.channels.core.rate_limit import (
    DISABLED_RATE_LIMIT,
    RateLimitConfig,
    RateLimiter,
)
from app.channels.core.reply_shortcuts import ReplyShortcutsMixin
from app.channels.reliability.retry import (
    RetryConfig,
    default_extract_retry_after,
    default_should_retry,
)
from app.channels.types import (
    ChannelActivity,
    ChannelCapabilities,
    ChannelHealth,
    ChannelIssue,
    ChannelStatus,
    GroupInfo,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
    StartMode,
)

if TYPE_CHECKING:
    from app.channels.core.credentials import (
        ChannelCredentialSpec,
    )
    from app.channels.protocols.async_login import LoginMethod


class BaseChannel(InboundPipelineMixin, ReplyShortcutsMixin, ProviderHooksMixin, ABC, EventEmitter):
    """Abstract base for channel providers.

    Subclasses must implement ``send`` and optionally override
    ``start`` / ``stop`` for long-lived connections (polling, WebSocket).

    For bidirectional channels, call ``_emit_inbound`` when a message
    arrives from the external platform. The Gateway will route it
    through the AgentRouter.

    Inbound pipeline (applied in ``_emit_inbound``):
        1. Bot self-message filter (``_bot_id``)
        2. Message deduplication (``_dedup_mode``: LRU or TTL)
        3. Rate limiting (``rate_limit_config``)
        4. Access control (``allow_policy``)
        5. Debounce (``_debounce_seconds``)
        6. Dispatch to handler

    Message deduplication supports two modes (``_dedup_mode``):
        - LRU (default): Pure capacity-based eviction (``_dedup_capacity``)
        - TTL (legacy): Time-based expiration (``_dedup_ttl``) + capacity limit

    Deduplication metrics (OpenTelemetry):
        - ``channel.dedup.hit``: Cache hits (duplicates skipped)
        - ``channel.dedup.miss``: Cache misses (new messages)
        - ``channel.dedup.eviction``: Cache evictions (LRU or TTL)

    Retry behavior: override ``retry_config``, ``should_retry``, or
    ``extract_retry_after`` for per-channel customization.

    Event system: Channels can emit events using ``self.emit(event_type, data)``.
    Gateway subscribes to events using ``channel.on(event_type, listener)``.
    """

    name: str = "base"
    channel_type: str = ""
    display_name: str = ""
    credential_spec: ChannelCredentialSpec | None = None
    capabilities: ChannelCapabilities = ChannelCapabilities()
    render_style: RenderStyle  # every concrete channel declares how its replies are rendered
    retry_config: RetryConfig = RetryConfig()
    allow_policy: AllowPolicy = SELECTIVE_POLICY
    rate_limit_config: RateLimitConfig = DISABLED_RATE_LIMIT
    supported_login_methods: ClassVar[list[LoginMethod]] = []
    start_mode: StartMode = StartMode.AUTO

    def should_auto_start(self) -> bool:
        """Whether Gateway should auto-start this channel during gateway.start().

        AUTO channels always return True.
        ON_DEMAND channels override this to return True only when a persisted
        session exists (enabling transparent reconnection after restart).
        """
        return self.start_mode == StartMode.AUTO

    @property
    def instance_id(self) -> str:
        """Derive instance_id from name and channel_type.

        For multi-instance channels named ``{channel_type}_{id}``, returns
        the ``{id}`` portion.  Returns ``""`` for default (non-instance) channels.
        """
        if self.channel_type and self.name.startswith(f"{self.channel_type}_"):
            return self.name[len(self.channel_type) + 1 :]
        return ""

    def extract_sender_locale(self, msg: InboundMessage) -> str | None:
        """Extract sender locale from platform-specific inbound metadata when available."""
        if not msg.metadata:
            return None
        for key in ("language_code", "sender_locale", "platform_locale"):
            value = msg.metadata.get(key)
            if value:
                return str(value)
        return None

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        """Create an instance from resolved credential values.

        Override in subclasses when constructor parameter names differ
        from the credential spec field names, or when type conversion
        is needed (e.g. str → int, str → bool, str → tuple).

        Default implementation passes all creds as keyword arguments.
        """
        return cls(**creds)

    def __init__(self) -> None:
        EventEmitter.__init__(self, self.name)
        self.__status = ChannelStatus.IDLE
        self.__connected = False
        self._inbound_handler: InboundHandler | None = None
        self._sender_gate: SenderGate | None = None
        self.health = ChannelHealth()
        self.activity = ChannelActivity()
        self._bot_id: str = ""
        self._seen_msg_ids: OrderedDict[str, float] = OrderedDict()
        self._debounce_tasks: dict[str, asyncio.Task[None]] = {}
        self._rate_limiter = RateLimiter(self.rate_limit_config)
        self._debounce_buffers: dict[str, InboundMessage] = {}

        meter = get_meter("myrm.channels")
        self._dedup_hit_counter = meter.create_counter(
            "channel.dedup.hit",
            description="Message deduplication cache hits",
        )
        self._dedup_miss_counter = meter.create_counter(
            "channel.dedup.miss",
            description="Message deduplication cache misses",
        )
        self._dedup_eviction_counter = meter.create_counter(
            "channel.dedup.eviction",
            description="Message deduplication cache evictions",
        )

    @property
    def _status(self) -> ChannelStatus:
        return self.__status

    @_status.setter
    def _status(self, new_status: ChannelStatus) -> None:
        old = self.__status
        self.__status = new_status
        if old != new_status:
            self.emit("status_change", {"old_status": old, "new_status": new_status})

    @property
    def is_connected(self) -> bool:
        return self.__connected

    def _set_connected(self, connected: bool) -> None:
        """Update connection state and emit ``connection_change`` on transitions."""
        if self.__connected == connected:
            return
        self.__connected = connected
        self.emit("connection_change", {"connected": connected})

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> str | None:
        """Deliver an outbound message through this channel.

        Returns the platform message id. The bus acknowledges a delivery only when this call returns
        normally, so every failure must raise ``ChannelSendError`` instead of returning quietly.
        Channels that cannot report ids declare ``capabilities.message_ids = False`` and return ``None``
        on success; for every other channel a ``None`` result for a message with text is treated as an
        unconfirmed delivery (media-only sends are exempt). When the platform accepted part of the
        message (for example the text but not an attachment), raise
        ``ChannelSendError(accepted=True, failed_attachments=...)`` so only the remainder is reported;
        ``accepted=True`` without names means only later text chunks are missing and nothing is re-sent;
        ``deliver_chunks`` raises it for a provider that posts its text chunk by chunk.
        Callers that need the outcome use ``MessageBus.send_now()`` (raises) or ``send_tracked()``
        (returns the id or ``None``); both bypass the queue.
        """

    async def start(self) -> None:
        """Start the channel (e.g. open WebSocket, begin polling).

        Subclasses that require authentication (QR scan, OAuth) before
        becoming truly connected should call ``_set_connected(True)``
        explicitly after auth succeeds instead of relying on this default.
        """
        self._status = ChannelStatus.RUNNING
        self.health.record_success()
        self._set_connected(True)

    async def stop(self) -> None:
        """Stop the channel and release resources.

        Release the channel's own task or connection and leave the status at ``STOPPED`` first, and do the best-effort
        network cleanup (drafts, streaming cards, commands) last: ``stop_channel`` abandons a stop that outlives its
        cap, and the steps it had not reached never run.
        """
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED

    async def health_check(self) -> bool:
        """Return True if the channel is healthy.

        Subclasses should override to perform real connectivity checks
        (e.g. Telegram ``getMe``, WhatsApp process alive).
        The Gateway calls this periodically and updates ``self.health``.
        """
        return self._status == ChannelStatus.RUNNING

    @property
    def status(self) -> ChannelStatus:
        return self._status

    def set_inbound_handler(self, handler: InboundHandler) -> None:
        """Register a callback for inbound messages (set by Gateway)."""
        self._inbound_handler = handler

    def set_sender_gate(self, gate: SenderGate) -> None:
        """Register the callback that answers whether the access policy admits a sender (set by the bus)."""
        self._sender_gate = gate

    async def start_typing(self, chat_id: str) -> None:
        """Send a typing/composing indicator to the chat. Override in subclasses."""

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator. Override in subclasses."""

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add a reaction emoji to a message; an empty emoji takes back the one this channel added.

        The empty emoji removes only what this channel put on the message: nothing when it put nothing, and never
        another member's reaction. A platform that refuses the request must raise, so the router reports it instead of
        showing a bot that silently has no status reaction. A channel that hands the request to a process which does
        not report back (the WhatsApp bridge) cannot raise for a refusal.
        """

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a placeholder message and return its message_id for later editing.

        Returns None if the channel does not support message editing.
        """
        return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit a previously sent message.

        A channel with ``capabilities.edit`` raises ``ChannelSendError`` when the platform did not apply the
        edit: callers fall back to a new message only on that signal. Other channels are never asked to edit.
        """

    async def pin_message(self, chat_id: str, message_id: str) -> None:
        """Pin a message in the chat. Override in subclasses."""

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Replace placeholder with a rich final message using full OutboundMessage context.

        Channels that support rich formatting (e.g. Feishu cards with sources/header)
        should override this to build structured output from the complete message.
        Default: falls back to edit_message with the text content. Like ``edit_message`` it raises
        ``ChannelSendError`` when the edit was not applied, so the router sends the reply as a new message.

        ``msg.content`` is already rendered (tool summary, sources and header included) and ``render()``
        returns such a message unchanged, so a channel may pass it through ``render()`` or send the content
        as it is, but must not decorate it again.
        """
        await self.edit_message(chat_id, message_id, msg.content)

    async def create_thread(
        self,
        chat_id: str,
        name: str,
        *,
        message_id: str | None = None,
    ) -> str | None:
        """Create a thread in the chat and return its thread_id.

        Args:
            chat_id: The channel/chat to create the thread in.
            name: Thread name/title (platform may truncate).
            message_id: If provided, create thread on this message.

        Returns:
            The thread ID if created, or None if not supported.
        """
        return None

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a previously sent message. No-op if not supported."""

    async def list_groups(self, force_refresh: bool = False) -> list[GroupInfo]:
        """Return groups the bot participates in.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data.

        Returns:
            List of groups the bot participates in.

        Override in subclasses that support group discovery.
        """
        return []

    def collect_issues(self) -> list[ChannelIssue]:
        """Collect structured diagnostic issues for this channel.

        Override in subclasses to provide channel-specific diagnostics.
        Default: derives a RUNTIME issue from ``health.last_error`` if present.
        """
        if self.health.last_error:
            return [
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            ]
        return []

    def should_retry(self, exc: BaseException) -> bool:
        """Whether *exc* is retryable. Override for channel-specific logic."""
        return default_should_retry(exc)

    def extract_retry_after(self, exc: BaseException) -> float | None:
        """Extract platform-specific retry-after seconds. Override for custom headers."""
        return default_extract_retry_after(exc)
