"""Telegram Rich Message outbound path — sendRichMessage with HTML fallback.

[INPUT]
- channels.rendering.renderer::render (POS: Channel message rendering pipeline.)
- channels.types::OutboundMessage, RenderStyle
- telegram.api::TelegramClient, TelegramApiError
- telegram.html_converter::split_markdown_rich

[OUTPUT]
- TelegramRichOutboundMixin: _try_send_rich for Bot API 10.1 native Markdown delivery

[POS]
Rich Message send helper mixin. Attempts sendRichMessage first; sets
_rich_send_available and returns None to trigger HTML fallback on the host channel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle

from .api import TelegramApiError

if TYPE_CHECKING:
    from .api import TelegramClient

logger = logging.getLogger(__name__)


class TelegramRichOutboundMixin:
    """Mixin providing Telegram Rich Message send with graceful degradation."""

    _client: TelegramClient
    _rich_render_style: RenderStyle
    _rich_send_available: bool | None

    async def _try_send_rich(
        self,
        msg: OutboundMessage,
        chat_id: str,
        reply_to: int | None,
        thread_id: int | None,
        reply_markup: dict[str, object] | None,
        notify_kwargs: dict[str, bool],
    ) -> str | None:
        """Attempt to send via ``sendRichMessage``. Returns message_id or None to fall back."""
        from .html_converter import split_markdown_rich

        chunks = render(msg, self._rich_render_style)
        parts = split_markdown_rich(chunks[0]) if chunks else []
        if not parts:
            return None

        last_mid: str | None = None
        for i, part in enumerate(parts):
            markup = reply_markup if (i == len(parts) - 1 and reply_markup) else None
            try:
                result = await self._client.send_rich_message(
                    chat_id,
                    part,
                    reply_to_message_id=reply_to,
                    message_thread_id=thread_id,
                    reply_markup=markup,
                    **notify_kwargs,
                )
                self._rich_send_available = True
                mid = result.get("message_id")
                if mid is not None:
                    last_mid = str(mid)
                reply_to = None
            except TelegramApiError as exc:
                if exc.is_method_not_found:
                    self._rich_send_available = False
                    if last_mid is not None:
                        return last_mid
                    logger.info("TelegramChannel: sendRichMessage unavailable, using HTML mode")
                    return None
                if exc.error_code == 400:
                    if last_mid is not None:
                        logger.warning("TelegramChannel: Rich partial send stopped (%s)", exc.description)
                        return last_mid
                    logger.warning("TelegramChannel: sendRichMessage rejected (%s), falling back to HTML", exc.description)
                    return None
                raise

        for remaining_chunk in chunks[1:]:
            for part in split_markdown_rich(remaining_chunk):
                try:
                    result = await self._client.send_rich_message(
                        chat_id, part, message_thread_id=thread_id, **notify_kwargs,
                    )
                    mid = result.get("message_id")
                    if mid is not None:
                        last_mid = str(mid)
                except TelegramApiError:
                    break

        return last_mid
