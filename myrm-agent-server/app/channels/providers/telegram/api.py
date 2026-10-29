"""Telegram Bot API async HTTP client.

[INPUT]
- telegram.api_core::TelegramApiError (POS: Bot API transport and the error a failed call raises)
- telegram.api_media::TelegramMediaApi (POS: media sending and file download group of the client)
- telegram.api_forum::TelegramForumApi (POS: Forum Topic group of the client)

[OUTPUT]
- TelegramClient: async Telegram Bot API client (bot_token, optional api_base)

[POS]
Telegram Bot API async HTTP client. Holds the text, interaction, command, webhook and rich-message calls; the media
and Forum Topic groups live in ``api_media`` and ``api_forum``, the transport in ``api_core``.
"""

from __future__ import annotations

from .api_core import TelegramApiError
from .api_forum import TelegramForumApi
from .api_media import TelegramMediaApi


class TelegramClient(TelegramMediaApi, TelegramForumApi):
    """Async client for Telegram Bot API.

    Uses a shared ``httpx.AsyncClient`` for connection pooling.

    Call ``close()`` during application shutdown to release resources.
    """

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def get_me(self) -> dict[str, object]:
        """``getMe`` — returns basic bot info."""
        return await self._call("getMe")

    async def verify_token(self) -> bool:
        """Verify the bot token is valid by calling ``getMe``."""
        try:
            await self.get_me()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Inbound (Long Polling)
    # ------------------------------------------------------------------

    async def get_updates(
        self,
        offset: int = 0,
        timeout: int = 30,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, object]]:
        """``getUpdates`` — long-polling for new updates."""
        params: dict[str, object] = {"timeout": timeout}
        if offset:
            params["offset"] = offset
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates

        result = await self._call(
            "getUpdates",
            json_data=params,
            timeout=float(timeout + 5),
        )
        return result if isinstance(result, list) else []

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    async def set_webhook(
        self,
        url: str,
        secret_token: str | None = None,
        allowed_updates: list[str] | None = None,
    ) -> bool:
        """``setWebhook`` — register a webhook URL."""
        params: dict[str, object] = {"url": url}
        if secret_token:
            params["secret_token"] = secret_token
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates
        await self._call("setWebhook", json_data=params)
        return True

    async def delete_webhook(self) -> bool:
        """``deleteWebhook`` — remove the current webhook."""
        await self._call("deleteWebhook", json_data={"drop_pending_updates": False})
        return True

    # ------------------------------------------------------------------
    # Outbound — text
    # ------------------------------------------------------------------

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict[str, object] | None = None,
        disable_web_page_preview: bool = True,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendMessage`` — send a text message."""
        params: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        if reply_to_message_id is not None:
            params["reply_parameters"] = {"message_id": reply_to_message_id}
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return await self._call("sendMessage", json_data=params)

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        rich_message: dict[str, object] | None = None,
        reply_markup: dict[str, object] | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``editMessageText`` — edit an existing message.

        When ``rich_message`` is provided (Bot API 10.1+), the message is edited
        as a Rich Message and ``text``/``parse_mode`` are ignored.
        """
        params: dict[str, object] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "disable_web_page_preview": True,
        }
        if rich_message is not None:
            params["rich_message"] = rich_message
        else:
            params["text"] = text
            params["parse_mode"] = parse_mode
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return await self._call("editMessageText", json_data=params)

    async def delete_message(self, chat_id: int | str, message_id: int) -> bool:
        """``deleteMessage`` — delete a message."""
        try:
            await self._call(
                "deleteMessage",
                json_data={"chat_id": chat_id, "message_id": message_id},
            )
            return True
        except TelegramApiError:
            return False

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def set_my_commands(self, commands: list[dict[str, str]]) -> bool:
        """``setMyCommands`` — register bot commands."""
        await self._call("setMyCommands", json_data={"commands": commands})
        return True

    async def delete_my_commands(self) -> bool:
        """``deleteMyCommands`` — remove registered commands."""
        try:
            await self._call("deleteMyCommands", json_data={})
            return True
        except TelegramApiError:
            return False

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    async def pin_chat_message(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        disable_notification: bool = True,
    ) -> None:
        """``pinChatMessage`` — pin a message in a chat."""
        await self._call(
            "pinChatMessage",
            json_data={
                "chat_id": chat_id,
                "message_id": message_id,
                "disable_notification": disable_notification,
            },
        )

    async def set_message_reaction(
        self,
        chat_id: int | str,
        message_id: int,
        reaction: list[dict[str, str]],
    ) -> None:
        """``setMessageReaction`` — add/remove emoji reactions (Bot API 7.2+)."""
        await self._call(
            "setMessageReaction",
            json_data={
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": reaction,
            },
        )

    async def answer_callback_query(self, callback_query_id: str) -> None:
        """``answerCallbackQuery`` — acknowledge a callback query."""
        try:
            await self._call(
                "answerCallbackQuery",
                json_data={"callback_query_id": callback_query_id},
                timeout=5.0,
            )
        except TelegramApiError:
            pass

    async def send_message_draft(
        self,
        chat_id: int | str,
        draft_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        message_thread_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendMessageDraft`` — non-public preview streaming API.

        Shows typing-style draft text in the chat input area without creating
        a permanent message. The same ``draft_id`` updates the existing draft;
        sending empty text clears it. Falls back gracefully when the endpoint
        is unavailable (older Bot API servers).
        """
        params: dict[str, object] = {
            "chat_id": chat_id,
            "draft_id": draft_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        return await self._call("sendMessageDraft", json_data=params)

    # ------------------------------------------------------------------
    # Outbound — Rich Messages (Bot API 10.1)
    # ------------------------------------------------------------------

    async def send_rich_message(
        self,
        chat_id: int | str,
        markdown: str,
        *,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        reply_markup: dict[str, object] | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendRichMessage`` — send a message with native rich formatting (Bot API 10.1).

        Passes raw Markdown directly to Telegram for native rendering of tables,
        math expressions, headings, collapsible blocks, and other rich constructs.
        Limit: 32768 UTF-8 characters, 500 blocks, 16 nesting levels.
        """
        params: dict[str, object] = {
            "chat_id": chat_id,
            "rich_message": {"markdown": markdown},
        }
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        if reply_to_message_id is not None:
            params["reply_parameters"] = {"message_id": reply_to_message_id}
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return await self._call("sendRichMessage", json_data=params)

    async def send_rich_message_draft(
        self,
        chat_id: int | str,
        draft_id: int,
        markdown: str,
        *,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        """``sendRichMessageDraft`` — stream a partial rich message (Bot API 10.1).

        Ephemeral 30-second preview for AI streaming. The final message must be
        persisted with ``send_rich_message``. Only available in private chats.
        """
        params: dict[str, object] = {
            "chat_id": chat_id,
            "draft_id": draft_id,
            "rich_message": {"markdown": markdown},
        }
        if message_thread_id is not None:
            params["message_thread_id"] = message_thread_id
        return await self._call("sendRichMessageDraft", json_data=params)

    async def send_chat_action(self, chat_id: int | str, action: str = "typing") -> None:
        """``sendChatAction`` — show typing indicator."""
        try:
            await self._call(
                "sendChatAction",
                json_data={"chat_id": chat_id, "action": action},
            )
        except TelegramApiError:
            pass
