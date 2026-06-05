"""Message side-effect helpers for AgentRouter.

Encapsulates typing indicators, reactions, placeholder management,
and reply convenience methods. These are best-effort operations that
silently ignore failures. Error replies use classified friendly messages
instead of raw internal errors.

[INPUT]
- channels.core.bus::MessageBus (POS: async message bus)
- channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.reliability.retry::send_with_retry (POS: async retry utility with exponential backoff)
- channels.rendering.splitter::split_message (POS: smart long-message splitting)
- llms.errors.classifier::classify_error, ErrorKind (POS: LLM error classification)

[OUTPUT]
- MessageEffects: Helper for typing/keepalive/reaction/placeholder/reply operations
- friendly_error_message(): Classify exception → user-friendly localized message with reference ID

[POS]
Message side-effect operations collection. Extracted from Router core routing logic,
encapsulating all auxiliary channel interaction operations. Router holds an instance via composition.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid
from functools import partial

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error

from app.channels.core.bus import (
    MessageBus,
    downgrade_components,
)
from app.channels.i18n import channel_t, get_text
from app.channels.reliability.retry import send_with_retry
from app.channels.types import (
    InboundMessage,
    MessagePriority,
    OutboundMessage,
)

logger = logging.getLogger(__name__)

_ERROR_KIND_KEYS: dict[ErrorKind, str] = {
    ErrorKind.RATE_LIMIT: "error_rate_limit",
    ErrorKind.OVERLOADED: "error_overloaded",
    ErrorKind.BILLING: "error_billing",
    ErrorKind.AUTH: "error_auth",
    ErrorKind.TIMEOUT: "error_timeout",
    ErrorKind.CONTEXT_OVERFLOW: "error_context_overflow",
    ErrorKind.FORMAT_ERROR: "error_format",
    ErrorKind.MODEL_NOT_FOUND: "error_model_not_found",
    ErrorKind.SAFETY_BLOCK: "error_safety_block",
    ErrorKind.RESPONSE_FORMAT_ERROR: "error_response_format",
    ErrorKind.UNKNOWN: "error_unknown",
}
assert set(_ERROR_KIND_KEYS) == set(ErrorKind), f"_ERROR_KIND_KEYS missing: {set(ErrorKind) - set(_ERROR_KIND_KEYS)}"


def _error_ref_id() -> str:
    """Short 8-char hex reference ID for correlating user-facing messages with logs."""
    return uuid.uuid4().hex[:8]


def friendly_error_message(
    exc: Exception,
    msg: InboundMessage | None = None,
    *,
    locale: str | None = None,
) -> tuple[str, str]:
    """Classify *exc* and return ``(friendly_message, ref_id)``.

    The friendly message is safe to display in any channel — it never
    contains internal error details. The ref_id links to the full error
    logged at ERROR level.
    """
    kind = classify_error(exc)
    ref_id = _error_ref_id()
    catalog_key = _ERROR_KIND_KEYS[kind]
    if msg is not None:
        base = get_text(msg, catalog_key)
    else:
        base = channel_t(locale, catalog_key)
    return f" {base} [ref: {ref_id}]", ref_id


class MessageEffects:
    """Stateless helper for message side-effects (typing, reactions, placeholders, replies).

    All operations are best-effort — failures are logged at debug level and silently ignored.
    """

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus
        self._typing_keepalive_tasks: dict[str, asyncio.Task[None]] = {}

    async def set_typing(self, channel: str, chat_id: str, *, composing: bool) -> None:
        """Best-effort typing indicator."""
        ch = self._bus.get_channel(channel)
        if not ch:
            return
        try:
            if composing:
                await ch.start_typing(chat_id)
            else:
                await ch.stop_typing(chat_id)
        except Exception as exc:
            logger.debug("typing indicator failed for %s/%s: %s", channel, chat_id, exc)

    def start_typing_keepalive(self, channel: str, chat_id: str) -> None:
        """Start periodic typing indicator refresh for platforms that auto-dismiss.

        Reads ``ChannelCapabilities.typing_keepalive_interval``; does nothing
        when the interval is 0 or the channel is missing.
        """
        ch = self._bus.get_channel(channel)
        if not ch:
            return
        interval = ch.capabilities.typing_keepalive_interval
        if interval <= 0:
            return

        key = f"{channel}:{chat_id}"
        existing = self._typing_keepalive_tasks.get(key)
        if existing and not existing.done():
            return

        async def _keepalive_loop() -> None:
            while True:
                await asyncio.sleep(interval)
                try:
                    await ch.start_typing(chat_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug(
                        "typing keepalive tick failed for %s/%s: %s",
                        channel,
                        chat_id,
                        exc,
                    )

        self._typing_keepalive_tasks[key] = asyncio.create_task(_keepalive_loop())

    async def stop_typing_keepalive(self, channel: str, chat_id: str) -> None:
        """Cancel the periodic typing refresh and send a stop indicator."""
        key = f"{channel}:{chat_id}"
        task = self._typing_keepalive_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def send_placeholder(
        self,
        channel: str,
        chat_id: str,
        *,
        thread_id: str | None = None,
        msg: InboundMessage | None = None,
    ) -> str | None:
        """Send a 'thinking...' placeholder message. Returns message_id or None."""
        ch = self._bus.get_channel(channel)
        if not ch:
            return None
        placeholder_text = get_text(msg, "placeholder_thinking") if msg is not None else channel_t(None, "placeholder_thinking")
        try:
            fn = partial(ch.send_placeholder, thread_id=thread_id)
            return await send_with_retry(
                fn,
                chat_id,
                placeholder_text,
                config=ch.retry_config,
                should_retry=ch.should_retry,
                extract_retry_after=ch.extract_retry_after,
                label=f"placeholder:{channel}",
            )
        except Exception as exc:
            logger.debug("placeholder send failed for %s/%s: %s", channel, chat_id, exc)
            return None

    async def edit_placeholder(
        self,
        channel: str,
        chat_id: str,
        placeholder_id: str,
        result: OutboundMessage,
    ) -> None:
        """Replace the placeholder with the actual Agent response.

        Prefers edit_placeholder_message (rich formatting with full message context)
        when the channel supports it, falling back to edit_message with text content.
        Falls back to normal outbound publish if editing fails entirely.
        """
        ch = self._bus.get_channel(channel)
        if not ch:
            await self._bus.publish_outbound(result)
            return

        result = downgrade_components(result, ch)

        from app.channels.rendering.splitter import (
            split_message,
        )

        max_len = ch.capabilities.max_text_length or 4096
        chunks = split_message(result.content, max_len)

        try:
            logger.debug("editing placeholder with %d chars", len(chunks[0]))
            first_result = dataclasses.replace(result, content=chunks[0])
            await send_with_retry(
                ch.edit_placeholder_message,
                chat_id,
                placeholder_id,
                first_result,
                config=ch.retry_config,
                should_retry=ch.should_retry,
                extract_retry_after=ch.extract_retry_after,
                label=f"edit:{channel}",
            )
            for extra_chunk in chunks[1:]:
                extra = dataclasses.replace(result, content=extra_chunk)
                await self._bus.publish_outbound(extra)
        except Exception as exc:
            logger.warning("placeholder edit failed, sending normally: %s", exc)
            await self._bus.publish_outbound(result)

    async def cleanup_placeholder(
        self,
        channel: str,
        chat_id: str,
        placeholder_id: str,
        error_text: str,
    ) -> None:
        """Replace an orphaned placeholder with an error/status message, or delete it."""
        ch = self._bus.get_channel(channel)
        if not ch:
            return
        try:
            await ch.edit_message(chat_id, placeholder_id, error_text)
        except Exception:
            try:
                await ch.delete_message(chat_id, placeholder_id)
            except Exception as exc:
                logger.debug("placeholder cleanup failed for %s/%s: %s", channel, chat_id, exc)

    async def edit_progress(
        self,
        channel: str,
        chat_id: str,
        placeholder_id: str | None,
        label: str,
    ) -> bool:
        """Best-effort edit of placeholder with a progress label.

        Returns:
            True if edit succeeded, False otherwise
        """
        if not placeholder_id:
            return False

        ch = self._bus.get_channel(channel)
        if not ch:
            return False
        try:
            await ch.edit_message(chat_id, placeholder_id, label)
            return True
        except Exception as exc:
            logger.debug("progress edit failed for %s/%s: %s", channel, chat_id, exc)
            return False

    async def set_reaction(
        self,
        channel: str,
        chat_id: str,
        message_id: object,
        emoji: str,
    ) -> None:
        """Best-effort message reaction."""
        if not isinstance(message_id, str) or not message_id:
            return
        ch = self._bus.get_channel(channel)
        if not ch or not ch.capabilities.reactions:
            return
        try:
            await ch.react_to_message(chat_id, message_id, emoji)
        except Exception as exc:
            logger.debug("reaction failed for %s/%s: %s", channel, chat_id, exc)

    async def ack_reaction(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None,
        emoji: str = "",
    ) -> None:
        """Add receive-acknowledgement reaction (used by ReactionPolicy.FULL)."""
        if not message_id:
            return
        await self.set_reaction(channel, chat_id, message_id, emoji)

    async def completion_reaction(
        self,
        channel: str,
        chat_id: str,
        message_id: str | None,
        *,
        success: bool,
        success_emoji: str = "",
        failure_emoji: str = "",
        had_ack: bool = False,
    ) -> None:
        """Add completion/failure reaction and remove prior ack if present."""
        if not message_id:
            return
        if had_ack:
            await self.set_reaction(channel, chat_id, message_id, "")
        await self.set_reaction(channel, chat_id, message_id, success_emoji if success else failure_emoji)

    async def send_error_reply(self, msg: InboundMessage, error: str | Exception) -> None:
        """Send a classified, user-friendly error reply.

        Accepts either a pre-formatted friendly string (from router's
        ``friendly_error_message`` call) or a raw Exception.

        Groups reply to chat_id; DMs reply to sender.
        """
        if isinstance(error, Exception):
            friendly, ref_id = friendly_error_message(error, msg)
            kind = classify_error(error)
            logger.error(
                "Channel error reply [ref: %s] [%s] for %s/%s: %s",
                ref_id,
                kind.value,
                msg.channel,
                msg.sender_id,
                error,
                exc_info=error,
            )
        else:
            friendly = error

        recipient = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=recipient,
            content=friendly,
            user_id=msg.user_id or "",
            reply_to_id=(
                (msg.message_id or str(msg.metadata["message_id"]))
                if msg.is_group and (msg.message_id or msg.metadata.get("message_id"))
                else None
            ),
            thread_id=msg.thread_id,
            priority=MessagePriority.SYSTEM,
        )
        await self._bus.publish_outbound(reply)

    async def send_pending_reply(self, msg: InboundMessage) -> None:
        """Notify the sender that their pairing is pending approval."""
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.sender_id,
            content=get_text(msg, "pairing_pending"),
            user_id="",
            thread_id=msg.thread_id,
            priority=MessagePriority.SYSTEM,
        )
        await self._bus.publish_outbound(reply)

    async def send_pairing_request_reply(self, msg: InboundMessage) -> None:
        """Notify the sender that a pairing request has been created."""
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.sender_id,
            content=get_text(msg, "pairing_submitted"),
            user_id="",
            thread_id=msg.thread_id,
            priority=MessagePriority.SYSTEM,
        )
        await self._bus.publish_outbound(reply)

    async def send_mute_reply(self, msg: InboundMessage) -> None:
        """Send a thread mute confirmation message."""
        recipient = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=recipient,
            content=get_text(msg, "mute_confirm"),
            user_id=msg.user_id or "",
            reply_to_id=msg.message_id or msg.metadata.get("message_id"),
            thread_id=msg.thread_id,
            priority=MessagePriority.SYSTEM,
        )
        await self._bus.publish_outbound(reply)

    @staticmethod
    async def wait_for_edit_gap(last_progress_at: float, min_interval: float = 2.0) -> None:
        """Ensure minimum interval since the last progress edit before the final edit.

        Prevents rapid successive edits that some messaging platforms
        (e.g. WhatsApp) may silently drop or process out-of-order.
        """
        if last_progress_at <= 0:
            return
        elapsed = time.monotonic() - last_progress_at
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
