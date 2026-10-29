"""Telegram Rich Message outbound path — sendRichMessage with HTML fallback.

[INPUT]
- channels.rendering.renderer::render (POS: Channel message rendering pipeline.)
- channels.types::OutboundMessage, RenderStyle
- telegram.api::TelegramClient
- telegram.api_core::TelegramApiError
- telegram.html_converter::split_markdown_rich
- channels.core.chunk_delivery::deliver_chunks (POS: ordered per-chunk delivery; a chunk after the first is retried alone, a failure there is a partial delivery)

[OUTPUT]
- TelegramRichOutboundMixin: _try_send_rich for Bot API 10.1 native Markdown delivery

[POS]
Rich Message send helper mixin. Attempts sendRichMessage first; sets
_rich_send_available and returns None to trigger HTML fallback on the host channel.
The parts of every rendered chunk are one ordered delivery: only a failure of the first
part falls back to HTML, a later part that fails is a partial delivery.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.core.chunk_delivery import deliver_chunks
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle

from .api_core import TelegramApiError

if TYPE_CHECKING:
    from app.channels.reliability.retry import RetryConfig

    from .api import TelegramClient
    from .notification import NotificationKwargs

logger = logging.getLogger(__name__)


class TelegramRichOutboundMixin:
    """Mixin providing Telegram Rich Message send with graceful degradation."""

    name: str
    retry_config: RetryConfig
    _client: TelegramClient
    _rich_render_style: RenderStyle
    _rich_send_available: bool | None

    if TYPE_CHECKING:

        def should_retry(self, exc: BaseException) -> bool: ...

        def extract_retry_after(self, exc: BaseException) -> float | None: ...

    async def _try_send_rich(
        self,
        msg: OutboundMessage,
        chat_id: str,
        reply_to: int | None,
        thread_id: int | None,
        reply_markup: dict[str, object] | None,
        notify_kwargs: NotificationKwargs,
    ) -> str | None:
        """Attempt to send via ``sendRichMessage``. Returns message_id or None to fall back.

        The parts of every rendered chunk go out as one ordered delivery: the quote rides the first part, the
        buttons the last. Only a failure of the first part falls back to HTML; a later one is a partial delivery.
        """
        from .html_converter import split_markdown_rich

        parts = [part for chunk in render(msg, self._rich_render_style) for part in split_markdown_rich(chunk)]
        if not parts:
            return None

        async def send_part(part: str, index: int) -> str | None:
            markup = reply_markup if (index == len(parts) - 1 and reply_markup) else None
            result = await self._client.send_rich_message(
                chat_id,
                part,
                reply_to_message_id=reply_to if index == 0 else None,
                message_thread_id=thread_id,
                reply_markup=markup,
                **notify_kwargs,
            )
            self._rich_send_available = True
            mid = result.get("message_id")
            return None if mid is None else str(mid)

        try:
            return await deliver_chunks(self, parts, send_part)
        except TelegramApiError as exc:
            # Only the first part raises it as is: nothing has been sent, so the HTML path can take over.
            if exc.is_method_not_found:
                self._rich_send_available = False
                logger.info("TelegramChannel: sendRichMessage unavailable, using HTML mode")
                return None
            if exc.error_code == 400:
                logger.warning("TelegramChannel: sendRichMessage rejected (%s), falling back to HTML", exc.description)
                return None
            raise
