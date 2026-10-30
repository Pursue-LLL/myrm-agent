"""Telegram long-polling loop with error classification.

Mixin providing the getUpdates loop used by TelegramChannel in polling mode. A 409 Conflict (another process polls
the same token) is retried a few times and then ends the channel; network errors back off exponentially and mark the
channel degraded.

[INPUT]
- telegram.helpers::_ALLOWED_UPDATES, POLL_TIMEOUT and the backoff and conflict constants
- telegram.models::TgUpdate (POS: Pydantic models for Telegram Bot API payloads)
- channels.types::ChannelStatus

[OUTPUT]
- TelegramPollingMixin: _poll_loop, _is_polling_conflict

[POS]
Telegram long-polling loop mixin. Each update goes through ``_parse_update``, ``_pre_emit_hook`` and ``_buffer_or_emit``, which
the host channel provides from its inbound, hooks and media-group parts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.channels.types import ChannelStatus

from .helpers import (
    _ALLOWED_UPDATES,
    _CONFLICT_RETRY_DELAY,
    _DEGRADED_THRESHOLD,
    _MAX_CONFLICT_RETRIES,
    _POLL_BACKOFF_FACTOR,
    _POLL_BACKOFF_INITIAL,
    _POLL_BACKOFF_MAX,
    POLL_TIMEOUT,
)
from .models import TgUpdate

if TYPE_CHECKING:
    from app.channels.types import ChannelHealth, InboundMessage

    from .api import TelegramClient

logger = logging.getLogger(__name__)


class TelegramPollingMixin:
    """Mixin providing the Telegram long-polling loop.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._status: ChannelStatus, self._offset: int
    - self.health, self._set_connected(connected), self._redact(text)
    - self._parse_update(update), self._pre_emit_hook(msg), self._buffer_or_emit(msg, update)
    """

    _client: TelegramClient
    _status: ChannelStatus
    _offset: int

    if TYPE_CHECKING:
        # Provided by the host channel (BaseChannel, TelegramInboundMixin, TelegramHooksMixin); declared with their
        # signatures for the type checker.
        health: ChannelHealth

        def _set_connected(self, connected: bool) -> None: ...
        def _redact(self, text: str) -> str: ...
        def _parse_update(self, update: dict[str, object]) -> InboundMessage | None: ...
        async def _pre_emit_hook(self, msg: InboundMessage) -> InboundMessage | None: ...
        async def _buffer_or_emit(self, msg: InboundMessage, update: dict[str, object]) -> None: ...

    @staticmethod
    def _is_polling_conflict(error: Exception) -> bool:
        """Detect Telegram 409 Conflict (another process polling same token)."""
        text = str(error).lower()
        return (
            "conflict" in type(error).__name__.lower()
            or "terminated by other getupdates request" in text
            or ("409" in text and "conflict" in text)
        )

    async def _poll_loop(self) -> None:
        """Long-polling loop with intelligent error classification.

        Classifies errors into two categories:
        - 409 Conflict: limited retries then mark ERROR (unrecoverable)
        - Network errors: exponential backoff with DEGRADED status feedback
        """
        backoff = _POLL_BACKOFF_INITIAL
        conflict_count = 0
        consecutive_errors = 0

        while self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            try:
                updates = await self._client.get_updates(
                    offset=self._offset,
                    timeout=POLL_TIMEOUT,
                    allowed_updates=_ALLOWED_UPDATES,
                )

                backoff = _POLL_BACKOFF_INITIAL
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    self._status = ChannelStatus.RUNNING
                    self.health.record_success()
                    self._set_connected(True)
                    logger.info("TelegramChannel: polling recovered")

                conflict_count = 0

                for raw_update in updates:
                    try:
                        tg = TgUpdate.model_validate(raw_update)
                    except ValidationError:
                        logger.debug("TelegramChannel: skipping invalid poll update")
                        continue

                    if tg.update_id:
                        self._offset = max(self._offset, tg.update_id + 1)

                    msg = self._parse_update(raw_update)
                    if msg:
                        msg = await self._pre_emit_hook(msg)
                        if msg:
                            await self._buffer_or_emit(msg, raw_update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_desc = self._redact(str(e))

                if self._is_polling_conflict(e):
                    conflict_count += 1
                    if conflict_count <= _MAX_CONFLICT_RETRIES:
                        logger.warning(
                            "TelegramChannel: polling conflict (%d/%d), "
                            "another process may be polling this token. "
                            "Retrying in %ds...",
                            conflict_count,
                            _MAX_CONFLICT_RETRIES,
                            int(_CONFLICT_RETRY_DELAY),
                        )
                        await asyncio.sleep(_CONFLICT_RETRY_DELAY)
                    else:
                        logger.error(
                            "TelegramChannel: polling conflict persists after %d "
                            "retries. Another process is actively polling this bot "
                            "token. Stopping polling.",
                            _MAX_CONFLICT_RETRIES,
                        )
                        self._status = ChannelStatus.ERROR
                        self.health.record_failure(
                            "Polling conflict: another process is polling this bot token. Stop the other process and restart."
                        )
                        self._set_connected(False)
                        break
                else:
                    consecutive_errors += 1
                    logger.warning(
                        "TelegramChannel: poll error (%d): %s",
                        consecutive_errors,
                        error_desc,
                    )
                    if consecutive_errors >= _DEGRADED_THRESHOLD:
                        self._status = ChannelStatus.DEGRADED
                        self.health.record_failure(error_desc)
                    await asyncio.sleep(min(backoff, _POLL_BACKOFF_MAX))
                    backoff = min(backoff * _POLL_BACKOFF_FACTOR, _POLL_BACKOFF_MAX)
