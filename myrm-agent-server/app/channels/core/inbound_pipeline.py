"""Inbound pipeline every channel shares: filter, dedup, rate limit, access check, debounce, dispatch.

[INPUT]
- channels.core.allow_policy::AllowPolicy (POS: inbound access control policy)
- channels.core.rate_limit::RateLimiter (POS: per-sender inbound rate limiting)
- channels.types::InboundMessage, ChannelStatus, ChannelActivity (POS: channel message and status types)

[OUTPUT]
- InboundHandler: callable the gateway registers to receive inbound messages
- SenderGate: callable the bus registers to answer whether the access policy admits a sender
- OwnerGate: callable the bus registers to answer whether a sender is the owner
- DedupMode: message deduplication mode (LRU or TTL)
- InboundPipelineMixin: ``_build_inbound`` / ``_emit_inbound`` and the pipeline stages behind them, and ``is_sender_admitted`` / ``is_sender_owner`` for work done before a message exists (a slash command, the transcription of an utterance)

[POS]
The inbound half of BaseChannel. Providers call ``_emit_inbound`` when the platform delivers a message; the state the
stages read (dedup cache, debounce buffers, rate limiter, handler) is created by ``BaseChannel.__init__``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING

from app.channels.types import ChannelStatus, InboundMessage

if TYPE_CHECKING:
    from collections import OrderedDict

    from opentelemetry.metrics import Counter

    from app.channels.core.allow_policy import AllowPolicy
    from app.channels.core.rate_limit import RateLimiter
    from app.channels.types import ChannelActivity

logger = logging.getLogger(__name__)

InboundHandler = Callable[[InboundMessage], Awaitable[None]]
SenderGate = Callable[[InboundMessage], Awaitable[bool]]
OwnerGate = Callable[[InboundMessage], Awaitable[bool]]

_DEFAULT_DEDUP_TTL = 120.0
_DEFAULT_DEDUP_CAPACITY = 2000


class DedupMode(Enum):
    """Message deduplication mode.

    - TTL: Time-based expiration (legacy, for backward compatibility)
    - LRU: Least Recently Used eviction (default, more efficient)
    """

    TTL = "ttl"
    LRU = "lru"


class InboundPipelineMixin:
    """Inbound pipeline of a channel: filter, dedup, rate limit, access check, debounce, dispatch."""

    # Provided by BaseChannel; declared for type checkers only.
    name: str
    allow_policy: AllowPolicy
    activity: ChannelActivity
    _status: ChannelStatus
    _bot_id: str
    _inbound_handler: InboundHandler | None
    _sender_gate: SenderGate | None
    _owner_gate: OwnerGate | None
    _seen_msg_ids: OrderedDict[str, float]
    _debounce_tasks: dict[str, asyncio.Task[None]]
    _debounce_buffers: dict[str, InboundMessage]
    _rate_limiter: RateLimiter
    _dedup_hit_counter: Counter
    _dedup_miss_counter: Counter
    _dedup_eviction_counter: Counter

    _dedup_mode: DedupMode = DedupMode.LRU
    _dedup_capacity: int = 1024
    _dedup_ttl: float = _DEFAULT_DEDUP_TTL
    _debounce_seconds: float = 0.0

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
            **kwargs,  # type: ignore[arg-type]  # forwarded as they come; the constructor rejects an unknown name
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

    async def is_sender_admitted(self, msg: InboundMessage) -> bool:
        """Whether the access policy admits ``msg``'s sender, for work done before ``msg`` is emitted.

        A user can act on the bot without sending it a message (a Discord slash command that moves it between voice
        channels), and a message can cost work before it exists (a spoken utterance is transcribed first). Such work
        follows the sender policy of the message it stands for. Nothing wired to a policy admits no one.
        """
        return self._sender_gate is not None and await self._sender_gate(msg)

    async def is_sender_owner(self, msg: InboundMessage) -> bool:
        """Whether ``msg``'s sender is the owner, for an action that needs more than admission.

        An action that acts on the owner's session rather than on the sender's own conversation (a Discord slash
        command that moves the bot between voice channels) is for the owner alone, as a system command is. Nothing
        wired has no owner.
        """
        return self._owner_gate is not None and await self._owner_gate(msg)

    async def _dispatch_inbound(self, msg: InboundMessage) -> None:
        """Final dispatch to the registered handler."""
        self.activity.record_inbound()
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
