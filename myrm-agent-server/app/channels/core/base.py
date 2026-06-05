"""Abstract base class for all channel providers.

Every channel (Chat, Telegram, Feishu, Webhook, …) implements this
interface so the Gateway can manage them uniformly.


[INPUT]
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.reliability.retry::RetryConfig, send_with_retry (POS: async retry utility with exponential backoff)
- channels.core.credentials::ChannelCredentialSpec (POS: framework-level credential type definition)

[OUTPUT]
- BaseChannel: abstract base class defining channel lifecycle and message send/receive interface

[POS]
Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly.
Supports outbound (send) and inbound (on_inbound callback) bidirectional communication.
Providers may declare credential_spec and from_credentials for self-contained credential management.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Self

from myrm_agent_harness.infra.tracing import get_meter

from app.channels.core.allow_policy import (
    SELECTIVE_POLICY,
    AllowPolicy,
)
from app.channels.core.events import EventEmitter
from app.channels.core.metrics import ChannelMetrics
from app.channels.core.rate_limit import (
    DISABLED_RATE_LIMIT,
    RateLimitConfig,
    RateLimiter,
)
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
    StartMode,
)

if TYPE_CHECKING:
    from app.channels.core.credentials import (
        ChannelCredentialSpec,
    )
    from app.channels.protocols.async_login import LoginMethod

logger = logging.getLogger(__name__)

InboundHandler = Callable[[InboundMessage], Awaitable[None]]

_DEFAULT_DEDUP_TTL = 120.0
_DEFAULT_DEDUP_CAPACITY = 2000


class DedupMode(Enum):
    """Message deduplication mode.

    - TTL: Time-based expiration (legacy, for backward compatibility)
    - LRU: Least Recently Used eviction (default, more efficient)
    """

    TTL = "ttl"
    LRU = "lru"


class BaseChannel(ABC, EventEmitter):
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

    _dedup_mode: DedupMode = DedupMode.LRU
    _dedup_capacity: int = 1024
    _dedup_ttl: float = _DEFAULT_DEDUP_TTL
    _debounce_seconds: float = 0.0

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
        self.health = ChannelHealth()
        self.activity = ChannelActivity()
        self.metrics = ChannelMetrics()
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

        Returns the platform message_id if available, or None.
        Callers that need the id (e.g. approval lifecycle) should use
        MessageBus.send_tracked() which bypasses the queue.
        """

    async def respond(
        self,
        incoming_msg: InboundMessage,
        content: str,
        *,
        in_thread: bool = True,
        **kwargs: object,
    ) -> str | None:
        """Reply to an incoming message with automatic context inference.

        Convenience wrapper for send() that automatically extracts:
        - channel: from self.name
        - recipient_id: from incoming_msg.chat_id (or sender_id as fallback)
        - user_id: from incoming_msg.user_id (or sender_id as fallback)
        - reply_to_id: from incoming_msg.message_id (if in_thread=True)

        Args:
            incoming_msg: The message to reply to
            content: Reply text content
            in_thread: If True, reply in thread (uses reply_to_id)
            **kwargs: Additional OutboundMessage fields (media, metadata, etc.)

        Returns:
            Platform message_id if available, or None

        Example:
            # Before (verbose)
            await channel.send(OutboundMessage(
                channel="slack",
                recipient_id=incoming_msg.chat_id,
                reply_to_id=incoming_msg.message_id,
                content="Hello!",
                user_id=incoming_msg.user_id
            ))

            # After (concise)
            await channel.respond(incoming_msg, "Hello!")
        """
        return await self.send(
            OutboundMessage(
                channel=self.name,
                recipient_id=incoming_msg.chat_id or incoming_msg.sender_id,
                content=content,
                user_id=incoming_msg.user_id or incoming_msg.sender_id,
                reply_to_id=incoming_msg.message_id if in_thread else None,
                **kwargs,  # type: ignore[arg-type]
            )
        )

    async def broadcast(
        self,
        recipient_id: str,
        content: str,
        user_id: str,
        *,
        thread_ts: str | None = None,
        **kwargs: object,
    ) -> str | None:
        """Send a proactive message to a channel or user.

        Convenience wrapper for send() for proactive messaging scenarios
        (cron jobs, notifications, alerts). Requires explicit user_id since
        it cannot be inferred from context.

        Args:
            recipient_id: Target channel_id or user_id
            content: Message text content
            user_id: User ID for audit/authorization (required)
            thread_ts: Optional thread timestamp (Slack-specific)
            **kwargs: Additional OutboundMessage fields (media, metadata, etc.)

        Returns:
            Platform message_id if available, or None

        Example:
            # Before (verbose)
            await channel.send(OutboundMessage(
                channel="slack",
                recipient_id="C12345",
                content="Cron job completed!",
                user_id=job.user_id,
                metadata={"job_name": "daily_report"}
            ))

            # After (concise)
            await channel.broadcast(
                "C12345",
                "Cron job completed!",
                user_id=job.user_id,
                metadata={"job_name": "daily_report"}
            )
        """
        metadata = kwargs.pop("metadata", None) or {}
        if thread_ts:
            metadata["thread_ts"] = thread_ts

        return await self.send(
            OutboundMessage(
                channel=self.name,
                recipient_id=recipient_id,
                content=content,
                user_id=user_id,
                metadata=metadata if metadata else None,  # type: ignore[arg-type]
                **kwargs,  # type: ignore[arg-type]
            )
        )

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
        """Stop the channel and release resources."""
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

    async def start_typing(self, chat_id: str) -> None:
        """Send a typing/composing indicator to the chat. Override in subclasses."""

    async def stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator. Override in subclasses."""

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add/remove a reaction emoji on a message. Empty emoji removes the reaction."""

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a placeholder message and return its message_id for later editing.

        Returns None if the channel does not support message editing.
        """
        return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit a previously sent message. No-op if not supported."""

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
        Default: falls back to edit_message with the text content.
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

    def _build_inbound(
        self,
        sender_id: str,
        content: str,
        chat_id: str,
        **kwargs: object,
    ) -> InboundMessage:
        """Build an InboundMessage with ``channel`` auto-populated from ``self.name``."""
        return InboundMessage(
            channel=self.name,
            sender_id=sender_id,
            content=content,
            chat_id=chat_id,
            **kwargs,
        )

    async def _emit_inbound(self, msg: InboundMessage) -> None:
        """Inbound pipeline: filter → dedup → rate limit → access check → debounce → dispatch.

        Called by channel implementations when a message arrives
        from the external platform. Subclasses should NOT override this;
        override individual pipeline stages if needed.
        """
        if self._status == ChannelStatus.DISABLED:
            return

        if self._bot_id and msg.sender_id == self._bot_id:
            return

        if msg.message_id and self._dedup_ttl > 0:
            now = time.monotonic()
            if msg.message_id in self._seen_msg_ids:
                self._dedup_hit_counter.add(1, {"channel": self.name})
                return
            self._dedup_miss_counter.add(1, {"channel": self.name})
            self._seen_msg_ids[msg.message_id] = now
            self._evict_expired_dedup(now)

        if not await self._rate_limiter.check_and_update(msg):
            self.metrics.record_rate_limit_hit()
            logger.debug(
                "Channel '%s': message from %s rate limited",
                self.name,
                msg.sender_id,
            )
            return

        reject_reason = self.allow_policy.evaluate(msg)
        if reject_reason is not None:
            logger.debug(
                "Channel '%s': message from %s denied (%s)",
                self.name,
                msg.sender_id,
                reject_reason.value,
            )
            return

        if self._debounce_seconds > 0:
            await self._debounce_emit(msg)
        else:
            await self._dispatch_inbound(msg)

    async def _dispatch_inbound(self, msg: InboundMessage) -> None:
        """Final dispatch to the registered handler."""
        self.activity.record_inbound()
        self.metrics.record_message()
        if self._inbound_handler:
            await self._inbound_handler(msg)
        else:
            logger.warning("Channel '%s': inbound message dropped (no handler)", self.name)

    async def _debounce_emit(self, msg: InboundMessage) -> None:
        """Buffer messages per chat_id and dispatch after debounce window."""
        key = msg.chat_id or msg.sender_id
        self._debounce_buffers[key] = msg

        existing = self._debounce_tasks.get(key)
        if existing and not existing.done():
            return

        async def _flush() -> None:
            await asyncio.sleep(self._debounce_seconds)
            buffered = self._debounce_buffers.pop(key, None)
            self._debounce_tasks.pop(key, None)
            if buffered:
                await self._dispatch_inbound(buffered)

        self._debounce_tasks[key] = asyncio.create_task(_flush())

    def _evict_expired_dedup(self, now: float) -> None:
        """Remove expired or excess entries from the dedup cache.

        Supports two modes:
        - LRU: Pure capacity-based eviction (faster, default)
        - TTL: Time-based expiration + capacity limit (legacy)
        """
        if self._dedup_mode == DedupMode.LRU:
            while len(self._seen_msg_ids) > self._dedup_capacity:
                self._seen_msg_ids.popitem(last=False)
                self._dedup_eviction_counter.add(1, {"channel": self.name, "mode": "lru"})
        else:
            while self._seen_msg_ids:
                oldest_key, oldest_ts = next(iter(self._seen_msg_ids.items()))
                if now - oldest_ts > self._dedup_ttl:
                    self._seen_msg_ids.pop(oldest_key)
                    self._dedup_eviction_counter.add(1, {"channel": self.name, "mode": "ttl"})
                else:
                    break
            while len(self._seen_msg_ids) > _DEFAULT_DEDUP_CAPACITY:
                self._seen_msg_ids.popitem(last=False)
                self._dedup_eviction_counter.add(1, {"channel": self.name, "mode": "ttl_capacity"})

    def register_routes(self, registrar: object) -> None:
        """Register channel-specific HTTP routes.

        Optional method. Channels that need custom HTTP endpoints
        (e.g., webhooks, login pages, status endpoints) can override
        this to register their routes.

        The registrar parameter is typed as object to avoid coupling the
        framework layer to any specific web framework. Business layer will
        provide a RouteRegistrar implementation.

        Example:
            from app.channels.protocols import (
                HttpMethod,
                RouteMetadata,
                RouteRegistrar,
            )

            def register_routes(self, registrar: object) -> None:
                if not isinstance(registrar, RouteRegistrar):
                    return

                registrar.add_route(
                    HttpMethod.POST,
                    "webhook",
                    self._handle_webhook,
                    RouteMetadata(
                        description="Receive webhook updates",
                        requires_auth=False,
                        rate_limit_policy="60 per minute",
                    ),
                )

        Args:
            registrar: Route registration interface (from business layer)
        """
        pass

    def _get_route_prefix(self) -> str:
        """Get the route prefix for this channel.

        Default: channels/{channel_name}/
        Can be overridden by subclasses for custom prefixes.

        Returns:
            Route prefix (without leading slash)
        """
        return f"channels/{self.name}/"

    async def start_login(
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ):
        """Start async login flow.

        Optional method. Channels that require user interaction for
        authentication (QR scan, OAuth2) should implement AsyncLoginProtocol
        and override this method.

        The method parameter is typed as object to avoid coupling the
        framework layer base class to specific protocol types. Implementations
        should import and use LoginMethod from protocols.async_login.

        Example:
            from app.channels.protocols import (
                AsyncLoginProtocol,
                LoginMethod,
                LoginEvent,
            )
            from app.channels.helpers import QRCodeLoginHelper

            class WeChatChannel(BaseChannel):
                supported_login_methods = [LoginMethod.QR_CODE]

                async def start_login(
                    self,
                    method: object,
                    *,
                    timeout: float = 300.0,
                    callback_url: str | None = None,
                ) -> AsyncIterator[LoginEvent]:
                    if method != LoginMethod.QR_CODE:
                        raise ValueError("Only QR_CODE method is supported")

                    helper = QRCodeLoginHelper(
                        fetch_qr_fn=self._fetch_qr_code,
                        poll_status_fn=self._poll_qr_status,
                    )
                    async for event in helper.run(timeout, self.name):
                        yield event

        Args:
            method: Login method to use (LoginMethod enum)
            timeout: Maximum seconds to wait for user action
            callback_url: OAuth2 callback URL (required for OAuth2 method)

        Yields:
            LoginEvent: State change events (see AsyncLoginProtocol)

        Raises:
            NotImplementedError: If channel does not support async login
        """
        raise NotImplementedError(
            f"{self.name} does not support async login (override start_login() and set supported_login_methods)"
        )

    async def cancel_login(self) -> None:
        """Cancel current login flow.

        Optional method. Channels implementing AsyncLoginProtocol should
        override this to stop background tasks and clean up resources.

        Default implementation does nothing (safe no-op).
        """
        pass

    async def handle_oauth2_callback(
        self,
        code: str | None,
        state: str,
        error: str | None = None,
    ) -> None:
        """Handle OAuth2 authorization callback.

        Called by the server-layer callback endpoint to deliver the
        authorization code to the running OAuth2 login flow.

        Channels using OAuth2LoginHelper should override this to delegate
        to helper.handle_callback(code, state, error).

        Args:
            code: Authorization code (if user authorized)
            state: CSRF state token (validated by OAuth2LoginHelper)
            error: OAuth2 error code (if user denied)

        Raises:
            NotImplementedError: If channel does not support OAuth2 login
        """
        raise NotImplementedError(f"{self.name} does not support OAuth2 callback")

    async def fetch_history(self, chat_id: str, limit: int = 15) -> list[InboundMessage]:
        """Fetch recent historical messages from the platform's chat/thread.

        Subclasses (like Discord, Slack, etc.) should override this method to
        retrieve actual history via platform-specific APIs. Filters out Bot
        and self messages dynamically.

        Args:
            chat_id: The ID of the channel/thread to fetch from.
            limit: The maximum number of historical messages to fetch.

        Returns:
            A list of InboundMessage objects sorted in ascending chronological order.
        """
        return []
