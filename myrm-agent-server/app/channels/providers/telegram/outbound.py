"""Telegram outbound messaging — send, edit, draft, reactions, and pins.

Mixin providing all outbound-related methods used by TelegramChannel.

[INPUT]
- channels.rendering.renderer::render (POS: Channel message rendering pipeline.)
- channels.types::OutboundMessage, RenderStyle
- telegram.api::TelegramClient, TelegramApiError
- telegram.helpers::build_inline_keyboard, send_media_attachment
- telegram.html_converter::md_to_telegram_html, split_message (POS: Markdown to Telegram HTML conversion and splitting.)
- telegram.outbound_rich::TelegramRichOutboundMixin (POS: Rich Message send with HTML fallback.)

[OUTPUT]
- TelegramOutboundMixin: send, edit, delete, react, pin, draft preview helpers

[POS]
Telegram outbound messaging mixin. Rich Message send/edit with HTML fallback,
sendMessageDraft streaming placeholders, and media attachment dispatch.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage, RenderStyle

from .api import TelegramApiError
from .helpers import build_inline_keyboard, send_media_attachment
from .html_converter import md_to_telegram_html, split_message
from .outbound_rich import TelegramRichOutboundMixin

if TYPE_CHECKING:
    from .api import TelegramClient

logger = logging.getLogger(__name__)

_MIN_DRAFT_CHARS = 20


class TelegramOutboundMixin(TelegramRichOutboundMixin):
    """Mixin providing Telegram outbound message delivery and editing.

    Requires the host class to have:
    - self._client: TelegramClient
    - self.render_style: RenderStyle
    - self._rich_render_style: RenderStyle
    - self._draft_counter, self._active_drafts, self._draft_available
    - self._rich_send_available, self._rich_draft_available
    - self._silent_notification_kwargs(), self._outbound_notification_kwargs(msg)
    """

    _client: TelegramClient
    render_style: RenderStyle
    _rich_render_style: RenderStyle
    _draft_counter: int
    _active_drafts: dict[str, int]
    _draft_available: bool | None
    _rich_send_available: bool | None
    _rich_draft_available: bool | None

    async def start_typing(self, chat_id: str) -> None:
        """Show 'typing...' indicator via sendChatAction."""
        await self._client.send_chat_action(chat_id, "typing")

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send media attachments then text chunks via Telegram Bot API.

        When Bot API 10.1 Rich Messages are available, sends raw Markdown via
        ``sendRichMessage`` for native tables/math/headings rendering. Falls back
        transparently to the HTML path on capability or parse errors.
        """
        chat_id = msg.recipient_id
        if not chat_id:
            return None
        last_message_id: str | None = None
        notify_kwargs = self._outbound_notification_kwargs(msg)

        for attachment in msg.media:
            await send_media_attachment(
                self._client,
                chat_id,
                attachment,
                msg.reply_to_id,
                notification_kwargs=notify_kwargs,
            )

        if msg.content:
            reply_markup = build_inline_keyboard(msg)
            reply_to = int(msg.reply_to_id) if msg.reply_to_id else None
            thread_id = int(msg.thread_id) if msg.thread_id else None

            if self._rich_send_available is not False:
                mid = await self._try_send_rich(msg, chat_id, reply_to, thread_id, reply_markup, notify_kwargs)
                if mid is not None:
                    return mid

            chunks = render(msg, self.render_style)
            for i, chunk in enumerate(chunks):
                html_text = md_to_telegram_html(chunk)
                for part in split_message(html_text):
                    markup = reply_markup if (i == len(chunks) - 1 and reply_markup) else None
                    try:
                        result = await self._client.send_message(
                            chat_id,
                            part,
                            reply_to_message_id=reply_to,
                            message_thread_id=thread_id,
                            reply_markup=markup,
                            **notify_kwargs,
                        )
                        mid = result.get("message_id")
                        if mid is not None:
                            last_message_id = str(mid)
                        reply_to = None
                    except TelegramApiError as exc:
                        if exc.is_parse_error:
                            logger.warning("TelegramChannel: HTML parse failed, retrying as plain text")
                            result = await self._client.send_message(
                                chat_id,
                                part,
                                parse_mode="",
                                reply_to_message_id=reply_to,
                                message_thread_id=thread_id,
                                **notify_kwargs,
                            )
                            mid = result.get("message_id")
                            if mid is not None:
                                last_message_id = str(mid)
                            reply_to = None
                        else:
                            raise

        return last_message_id

    def _allocate_draft_id(self) -> int:
        self._draft_counter = (self._draft_counter % 2_147_483_647) + 1
        return self._draft_counter

    def _draft_key(self, chat_id: str, message_id: str) -> str:
        return f"{chat_id}:{message_id}"

    async def _try_send_draft(self, chat_id: str, text: str, *, thread_id: str | None = None) -> int | None:
        """Attempt to send a draft preview. Returns draft_id on success, None if unavailable.

        Tries Rich Message draft first (Bot API 10.1) for native formatting, then
        falls back to HTML sendMessageDraft, then returns None for edit-based streaming.
        """
        tid = int(thread_id) if thread_id else None
        silent = self._silent_notification_kwargs()
        draft_id = self._allocate_draft_id()

        if self._rich_draft_available is not False:
            try:
                await self._client.send_rich_message_draft(
                    chat_id, draft_id, text, message_thread_id=tid,
                )
                self._rich_draft_available = True
                return draft_id
            except TelegramApiError as exc:
                if exc.is_method_not_found:
                    self._rich_draft_available = False
                    logger.info("TelegramChannel: sendRichMessageDraft unavailable")
                elif "can't be used" in exc.description.lower() or "can be used only" in exc.description.lower():
                    pass
                elif exc.error_code >= 500:
                    raise
                else:
                    self._rich_draft_available = False

        if self._draft_available is False:
            return None
        try:
            await self._client.send_message_draft(
                chat_id,
                draft_id,
                md_to_telegram_html(text),
                message_thread_id=tid,
                **silent,
            )
            self._draft_available = True
            return draft_id
        except TelegramApiError as exc:
            desc = exc.description.lower()
            if "unknown method" in desc or "not found" in desc or "not available" in desc or "not supported" in desc:
                self._draft_available = False
                logger.info("TelegramChannel: sendMessageDraft unavailable, using edit mode")
                return None
            if "can't be used" in desc or "can be used only" in desc:
                return None
            raise

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a placeholder via draft preview (DM) or regular message (fallback).

        When sendMessageDraft is available, the placeholder appears as a
        typing-style draft in the recipient's input area -- no push
        notification, no message flicker. On API unavailability or group
        chats, falls back to a regular message for editing.
        """
        silent = self._silent_notification_kwargs()
        draft_id = await self._try_send_draft(chat_id, text, thread_id=thread_id)
        if draft_id is not None:
            placeholder_id = f"draft:{draft_id}"
            self._active_drafts[self._draft_key(chat_id, placeholder_id)] = draft_id
            return placeholder_id

        try:
            tid = int(thread_id) if thread_id else None
            result = await self._client.send_message(
                chat_id,
                md_to_telegram_html(text),
                message_thread_id=tid,
                **silent,
            )
            return str(result.get("message_id", ""))
        except TelegramApiError as exc:
            if exc.is_parse_error:
                result = await self._client.send_message(
                    chat_id,
                    text,
                    parse_mode="",
                    message_thread_id=int(thread_id) if thread_id else None,
                    **silent,
                )
                return str(result.get("message_id", ""))
            logger.warning("TelegramChannel: placeholder failed: %s", exc)
            return None

    def _is_draft_id(self, message_id: str) -> bool:
        return message_id.startswith("draft:")

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit a message or update a draft preview.

        Draft updates are suppressed until text exceeds ``_MIN_DRAFT_CHARS``
        to avoid rapid visual flicker during the first few streaming tokens.
        Rich Message draft path is used when ``_rich_draft_available`` is True.
        """
        draft_key = self._draft_key(chat_id, message_id)
        draft_id = self._active_drafts.get(draft_key)
        silent = self._silent_notification_kwargs()

        if draft_id is not None:
            if len(text) < _MIN_DRAFT_CHARS:
                return
            if self._rich_draft_available is True:
                try:
                    await self._client.send_rich_message_draft(chat_id, draft_id, text)
                    return
                except TelegramApiError:
                    pass
            try:
                await self._client.send_message_draft(
                    chat_id,
                    draft_id,
                    md_to_telegram_html(text),
                    **silent,
                )
                return
            except TelegramApiError:
                pass

        if self._is_draft_id(message_id):
            return

        if self._rich_send_available is True:
            try:
                await self._client.edit_message_text(
                    chat_id,
                    int(message_id),
                    text,
                    rich_message={"markdown": text},
                    **silent,
                )
                return
            except TelegramApiError as exc:
                if exc.is_not_modified:
                    return
                if exc.error_code != 400:
                    logger.warning("TelegramChannel: rich edit failed: %s", exc)

        try:
            await self._client.edit_message_text(
                chat_id,
                int(message_id),
                md_to_telegram_html(text),
                **silent,
            )
        except TelegramApiError as exc:
            if exc.is_not_modified:
                return
            if exc.is_parse_error:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        text,
                        parse_mode="",
                        **silent,
                    )
                except TelegramApiError as inner:
                    if not inner.is_not_modified:
                        logger.warning("TelegramChannel: edit failed: %s", inner)
                return
            logger.warning("TelegramChannel: edit failed: %s", exc)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Finalize a placeholder: materialize draft into a permanent message, or edit in-place.

        When Rich Messages are available, the final message is sent/edited with
        native formatting; falls back to HTML then plain text on any failure.
        """
        notify_kwargs = self._outbound_notification_kwargs(msg)
        silent = self._silent_notification_kwargs()
        reply_markup = build_inline_keyboard(msg)

        draft_key = self._draft_key(chat_id, message_id)
        draft_id = self._active_drafts.pop(draft_key, None)
        if draft_id is not None:
            try:
                await self._client.send_message_draft(chat_id, draft_id, "", **silent)
            except TelegramApiError:
                pass

            thread_id = int(msg.thread_id) if msg.thread_id else None

            if self._rich_send_available is not False:
                rich_chunks = render(msg, self._rich_render_style)
                if rich_chunks:
                    try:
                        await self._client.send_rich_message(
                            chat_id,
                            rich_chunks[0],
                            message_thread_id=thread_id,
                            reply_markup=reply_markup,
                            **notify_kwargs,
                        )
                        self._rich_send_available = True
                        return
                    except TelegramApiError as exc:
                        if exc.is_method_not_found:
                            self._rich_send_available = False
                        elif exc.error_code >= 500:
                            raise

            chunks = render(msg, self.render_style)
            html_text = md_to_telegram_html(chunks[0]) if chunks else ""
            try:
                await self._client.send_message(
                    chat_id,
                    html_text,
                    message_thread_id=thread_id,
                    reply_markup=reply_markup,
                    **notify_kwargs,
                )
            except TelegramApiError as exc:
                if exc.is_parse_error:
                    await self._client.send_message(
                        chat_id,
                        chunks[0] if chunks else "",
                        parse_mode="",
                        message_thread_id=thread_id,
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                else:
                    logger.warning("TelegramChannel: draft materialize failed: %s", exc)
            return

        if self._rich_send_available is True:
            rich_chunks = render(msg, self._rich_render_style)
            if rich_chunks:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        rich_chunks[0],
                        rich_message={"markdown": rich_chunks[0]},
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                    return
                except TelegramApiError as exc:
                    if exc.is_not_modified:
                        return
                    if exc.error_code >= 500:
                        raise

        chunks = render(msg, self.render_style)
        html_text = md_to_telegram_html(chunks[0]) if chunks else ""
        try:
            await self._client.edit_message_text(
                chat_id,
                int(message_id),
                html_text,
                reply_markup=reply_markup,
                **notify_kwargs,
            )
        except TelegramApiError as exc:
            if exc.is_not_modified:
                return
            if exc.is_parse_error:
                try:
                    await self._client.edit_message_text(
                        chat_id,
                        int(message_id),
                        chunks[0] if chunks else "",
                        parse_mode="",
                        reply_markup=reply_markup,
                        **notify_kwargs,
                    )
                except TelegramApiError as inner:
                    if not inner.is_not_modified:
                        logger.warning("TelegramChannel: edit_placeholder failed: %s", inner)
                return
            logger.warning("TelegramChannel: edit_placeholder failed: %s", exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a message via deleteMessage. Draft-only placeholders are silently skipped."""
        if self._is_draft_id(message_id):
            draft_key = self._draft_key(chat_id, message_id)
            draft_id = self._active_drafts.pop(draft_key, None)
            if draft_id is not None:
                try:
                    silent = self._silent_notification_kwargs()
                    await self._client.send_message_draft(chat_id, draft_id, "", **silent)
                except TelegramApiError:
                    pass
            return
        await self._client.delete_message(chat_id, int(message_id))

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add or remove a reaction via setMessageReaction (Bot API 7.2+)."""
        reaction = [{"type": "emoji", "emoji": emoji}] if emoji else []
        await self._client.set_message_reaction(chat_id, int(message_id), reaction)

    async def pin_message(self, chat_id: str, message_id: str) -> None:
        """Pin a message in a chat."""
        try:
            await self._client.pin_chat_message(chat_id, int(message_id))
        except TelegramApiError as exc:
            logger.warning("TelegramChannel: pin failed: %s", exc)
