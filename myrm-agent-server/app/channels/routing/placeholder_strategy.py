"""Adaptive placeholder timing — defer noisy placeholders for fast short replies."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from app.channels.types import OutboundMessage

logger = logging.getLogger(__name__)

DEFER_SECONDS = 0.18
SHORT_CIRCUIT_UTF16_MAX = 320

SendPlaceholderFn = Callable[[], Awaitable[str | None]]


def utf16_len(text: str) -> int:
    """Return Telegram-compatible UTF-16 code unit length."""
    return len(text.encode("utf-16-le")) // 2


def qualifies_short_circuit(result: OutboundMessage) -> bool:
    """True when a final reply is short enough to skip placeholder entirely."""
    if result.tool_steps:
        return False
    return utf16_len(result.content) <= SHORT_CIRCUIT_UTF16_MAX


class DeferredPlaceholder:
    """Defer placeholder send by ``DEFER_SECONDS``; cancel on short-circuit delivery."""

    __slots__ = ("_cancelled", "_done", "_had_activity", "_placeholder_id", "_send_fn", "_task")

    def __init__(self) -> None:
        self._task: asyncio.Task[str | None] | None = None
        self._send_fn: SendPlaceholderFn | None = None
        self._placeholder_id: str | None = None
        self._done = asyncio.Event()
        self._cancelled = False
        self._had_activity = False

    @property
    def placeholder_id(self) -> str | None:
        return self._placeholder_id

    def start(self, send_fn: SendPlaceholderFn) -> None:
        self._send_fn = send_fn

        async def _run() -> str | None:
            try:
                await asyncio.sleep(DEFER_SECONDS)
                if self._cancelled or self._placeholder_id is not None or self._send_fn is None:
                    return self._placeholder_id
                self._placeholder_id = await self._send_fn()
                return self._placeholder_id
            finally:
                self._done.set()

        self._task = asyncio.create_task(_run())

    async def mark_activity(self) -> None:
        """Record stream activity and eagerly materialize placeholder if still pending."""
        self._had_activity = True
        if self._cancelled or self._placeholder_id is not None or self._send_fn is None:
            return
        self._placeholder_id = await self._send_fn()
        self._done.set()

    async def cancel(self) -> None:
        """Cancel pending defer; no-op once placeholder was sent."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def wait_for_id(self) -> str | None:
        """Wait until defer completes (sent or cancelled) and return placeholder id."""
        if self._task is None:
            return None
        if not self._done.is_set():
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("Deferred placeholder task cancelled")
        return self._placeholder_id

    async def resolve_for_delivery(self, result: OutboundMessage | None) -> str | None:
        """Apply short-circuit only when defer has not completed yet."""
        if not self._done.is_set():
            if (
                result is not None
                and qualifies_short_circuit(result)
                and not self._had_activity
            ):
                await self.cancel()
                return None
            return await self.wait_for_id()
        return self._placeholder_id
