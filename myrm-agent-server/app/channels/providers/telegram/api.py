"""Telegram Bot API async HTTP client with automatic endpoint fallback.

Supports custom ``api_base`` for self-hosted Bot API servers. When using
the official ``api.telegram.org``, maintains a fallback chain of known
Telegram server IPs — on network failures the client switches endpoint
and sticks to the first that succeeds.

[INPUT]  bot_token, api_base (optional)
[OUTPUT] TelegramApiError, TelegramClient, get_recommended_send_method
[POS] Telegram Bot API async HTTP client. Encapsulates all Bot API HTTP calls (messaging,
media, commands, reactions, Forum Topic CRUD) with automatic endpoint fallback.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_API_HOST = "api.telegram.org"
_API_BASE = f"https://{_API_HOST}/bot{{token}}"
_FILE_BASE = f"https://{_API_HOST}/file/bot{{token}}"
_TIMEOUT = 30.0
_UPLOAD_TIMEOUT = 60.0

_FALLBACK_IPS: tuple[str, ...] = (
    "149.154.167.220",
    "149.154.175.50",
    "91.108.56.165",
)

_NETWORK_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    OSError,
)


class TelegramApiError(Exception):
    """Raised when the Telegram Bot API returns ok=false."""

    def __init__(self, error_code: int, description: str, parameters: dict[str, object] | None = None) -> None:
        self.error_code = error_code
        self.description = description
        self.parameters = parameters or {}
        super().__init__(f"Telegram API {error_code}: {description}")

    @property
    def is_parse_error(self) -> bool:
        return self.error_code == 400 and "can't parse entities" in self.description.lower()

    @property
    def is_not_modified(self) -> bool:
        return self.error_code == 400 and "message is not modified" in self.description.lower()

    @property
    def is_method_not_found(self) -> bool:
        desc = self.description.lower()
        return self.error_code == 404 or (
            self.error_code == 400
            and ("method" in desc or "endpoint" in desc)
            and ("not found" in desc or "does not exist" in desc)
        )


class TelegramClient:
    """Async client for Telegram Bot API.

    Uses a shared ``httpx.AsyncClient`` for connection pooling.
    When no custom ``api_base`` is set, the client maintains a fallback
    chain of known Telegram server IPs and automatically switches on
    network-level failures (DNS / connect / timeout).

    Call ``close()`` during application shutdown to release resources.
    """

    def __init__(self, token: str, *, api_base: str | None = None) -> None:
        self._token = token
        self._http: httpx.AsyncClient | None = None

        if api_base:
            base = api_base.rstrip("/")
            self._api_bases = [f"{base}/bot{token}"]
            self._file_bases = [f"{base}/file/bot{token}"]
        else:
            official = _API_BASE.format(token=token)
            official_file = _FILE_BASE.format(token=token)
            ip_api = [f"https://{ip}/bot{token}" for ip in _FALLBACK_IPS]
            ip_file = [f"https://{ip}/file/bot{token}" for ip in _FALLBACK_IPS]
            self._api_bases = [official, *ip_api]
            self._file_bases = [official_file, *ip_file]

        self._active_idx = 0

    @property
    def token(self) -> str:
        return self._token

    @property
    def _base(self) -> str:
        return self._api_bases[self._active_idx]

    @property
    def _file_base(self) -> str:
        return self._file_bases[self._active_idx]

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    def _host_headers(self, idx: int) -> dict[str, str]:
        """Return Host header when talking to a fallback IP endpoint."""
        if idx > 0 and len(self._api_bases) > 1:
            return {"Host": _API_HOST}
        return {}

    async def _call(
        self,
        method: str,
        *,
        json_data: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
        timeout: float = _TIMEOUT,
    ) -> dict[str, object]:
        """Unified Bot API call with automatic endpoint fallback.

        On network-level failures the client cycles through fallback
        endpoints and sticks to the first that succeeds.
        """
        last_exc: BaseException | None = None
        http = self._get_http()

        for offset in range(len(self._api_bases)):
            idx = (self._active_idx + offset) % len(self._api_bases)
            url = f"{self._api_bases[idx]}/{method}"
            hdrs = self._host_headers(idx)

            try:
                resp = await (
                    http.post(url, data=data or {}, files=files, timeout=timeout, headers=hdrs)
                    if files
                    else http.post(url, json=json_data or {}, timeout=timeout, headers=hdrs)
                )
            except _NETWORK_ERRORS as exc:
                last_exc = exc
                if offset == 0 and len(self._api_bases) > 1:
                    logger.warning("Telegram endpoint unreachable (%s), trying fallback", type(exc).__name__)
                continue

            if idx != self._active_idx:
                logger.info("Telegram fallback succeeded, sticky to endpoint %d", idx)
                self._active_idx = idx

            body: dict[str, object] = resp.json()
            if not body.get("ok"):
                code = int(body.get("error_code", resp.status_code))
                desc = str(body.get("description", "Unknown error"))
                params = body.get("parameters")
                raise TelegramApiError(code, desc, params if isinstance(params, dict) else None)

            return body.get("result", {})  # type: ignore[return-value]

        raise last_exc  # type: ignore[misc]

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

    # ------------------------------------------------------------------
    # Forum Topics (Bot API 6.3+)
    # ------------------------------------------------------------------

    async def create_forum_topic(
        self,
        chat_id: int | str,
        name: str,
        *,
        icon_color: int | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> dict[str, object]:
        """``createForumTopic`` — create a topic in a Forum supergroup chat."""
        params: dict[str, object] = {"chat_id": chat_id, "name": name}
        if icon_color is not None:
            params["icon_color"] = icon_color
        if icon_custom_emoji_id is not None:
            params["icon_custom_emoji_id"] = icon_custom_emoji_id
        return await self._call("createForumTopic", json_data=params)

    async def edit_forum_topic(
        self,
        chat_id: int | str,
        message_thread_id: int,
        *,
        name: str | None = None,
        icon_custom_emoji_id: str | None = None,
    ) -> bool:
        """``editForumTopic`` — rename or change icon of a topic."""
        params: dict[str, object] = {
            "chat_id": chat_id,
            "message_thread_id": message_thread_id,
        }
        if name is not None:
            params["name"] = name
        if icon_custom_emoji_id is not None:
            params["icon_custom_emoji_id"] = icon_custom_emoji_id
        await self._call("editForumTopic", json_data=params)
        return True

    async def close_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``closeForumTopic`` — close a topic (stops new messages)."""
        await self._call(
            "closeForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True

    async def reopen_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``reopenForumTopic`` — reopen a closed topic."""
        await self._call(
            "reopenForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True

    async def delete_forum_topic(self, chat_id: int | str, message_thread_id: int) -> bool:
        """``deleteForumTopic`` — delete a topic and all its messages."""
        await self._call(
            "deleteForumTopic",
            json_data={"chat_id": chat_id, "message_thread_id": message_thread_id},
        )
        return True

    # ------------------------------------------------------------------
    # Media (unified via _send_media)
    # ------------------------------------------------------------------

    async def _send_media(
        self,
        api_method: str,
        field: str,
        chat_id: int | str,
        payload: bytes | str,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        params: dict[str, object] = {"chat_id": chat_id}
        if caption:
            params["caption"] = caption
            params["parse_mode"] = "HTML"
        if reply_to_message_id is not None:
            params["reply_to_message_id"] = reply_to_message_id
        if disable_notification is not None:
            params["disable_notification"] = disable_notification
        if isinstance(payload, bytes):
            form_data: dict[str, str] = {}
            for key, value in params.items():
                if isinstance(value, bool):
                    form_data[str(key)] = "true" if value else "false"
                else:
                    form_data[str(key)] = str(value)
            return await self._call(
                api_method,
                files={field: (filename, payload, mime_type)},
                data=form_data,
                timeout=_UPLOAD_TIMEOUT,
            )
        params[field] = payload
        return await self._call(api_method, json_data=params)

    async def send_photo(
        self,
        chat_id: int | str,
        photo: bytes | str,
        *,
        filename: str = "photo.jpg",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendPhoto`` — upload and send a photo (bytes) or by URL (str)."""
        return await self._send_media(
            "sendPhoto",
            "photo",
            chat_id,
            photo,
            filename=filename,
            mime_type="image/jpeg",
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )

    async def send_document(
        self,
        chat_id: int | str,
        document: bytes | str,
        filename: str = "file",
        *,
        mime_type: str = "application/octet-stream",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendDocument`` — upload and send a document."""
        return await self._send_media(
            "sendDocument",
            "document",
            chat_id,
            document,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )

    async def send_voice(
        self,
        chat_id: int | str,
        voice: bytes | str,
        *,
        filename: str = "voice.ogg",
        mime_type: str = "audio/ogg",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendVoice`` — upload and send a voice message (OGG/OPUS formats only).

        Telegram supports voice messages in OGG with OPUS codec or OPUS format.
        Other audio formats (MP3, M4A) should use send_audio() instead.

        Args:
            chat_id: Target chat or user ID
            voice: Voice data (bytes) or file_id (str) from previous upload
            filename: Filename for the voice message (default: voice.ogg)
            mime_type: MIME type (must be audio/ogg or audio/opus)
            caption: Optional caption text
            reply_to_message_id: Optional message to reply to

        Returns:
            Telegram API response with message details

        Raises:
            ValueError: If mime_type is not supported for sendVoice
            VoiceMessageTooLargeError: If voice data exceeds 50MB limit
        """
        from .constants import TELEGRAM_VOICE_MAX_SIZE, VOICE_MIME_TYPES
        from .exceptions import VoiceMessageTooLargeError

        if mime_type not in VOICE_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type for sendVoice: {mime_type}. "
                f"Supported types: {', '.join(sorted(VOICE_MIME_TYPES))}. "
                f"For MP3/M4A formats, use send_audio() instead."
            )

        if isinstance(voice, bytes) and len(voice) > TELEGRAM_VOICE_MAX_SIZE:
            raise VoiceMessageTooLargeError(actual_size=len(voice), max_size=TELEGRAM_VOICE_MAX_SIZE)

        return await self._send_media(
            "sendVoice",
            "voice",
            chat_id,
            voice,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )

    async def send_audio(
        self,
        chat_id: int | str,
        audio: bytes | str,
        *,
        filename: str = "audio.mp3",
        mime_type: str = "audio/mpeg",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendAudio`` — upload and send an audio file (MP3/M4A formats).

        Telegram supports audio files in MP3 and M4A formats via sendAudio.
        For voice messages (OGG/OPUS), use send_voice() instead.

        Args:
            chat_id: Target chat or user ID
            audio: Audio data (bytes) or file_id (str) from previous upload
            filename: Filename for the audio file (default: audio.mp3)
            mime_type: MIME type (must be audio/mpeg, audio/mp4, or audio/m4a)
            caption: Optional caption text
            reply_to_message_id: Optional message to reply to

        Returns:
            Telegram API response with message details

        Raises:
            ValueError: If mime_type is not supported for sendAudio
            AudioFileTooLargeError: If audio data exceeds 50MB limit
        """
        from .constants import AUDIO_MIME_TYPES, TELEGRAM_AUDIO_MAX_SIZE
        from .exceptions import AudioFileTooLargeError

        if mime_type not in AUDIO_MIME_TYPES:
            raise ValueError(
                f"Unsupported MIME type for sendAudio: {mime_type}. "
                f"Supported types: {', '.join(sorted(AUDIO_MIME_TYPES))}. "
                f"For OGG/OPUS formats, use send_voice() instead."
            )

        if isinstance(audio, bytes) and len(audio) > TELEGRAM_AUDIO_MAX_SIZE:
            raise AudioFileTooLargeError(actual_size=len(audio), max_size=TELEGRAM_AUDIO_MAX_SIZE)

        return await self._send_media(
            "sendAudio",
            "audio",
            chat_id,
            audio,
            filename=filename,
            mime_type=mime_type,
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )

    async def send_video(
        self,
        chat_id: int | str,
        video: bytes | str,
        *,
        filename: str = "video.mp4",
        caption: str | None = None,
        reply_to_message_id: int | None = None,
        disable_notification: bool | None = None,
    ) -> dict[str, object]:
        """``sendVideo`` — upload and send a video."""
        return await self._send_media(
            "sendVideo",
            "video",
            chat_id,
            video,
            filename=filename,
            mime_type="video/mp4",
            caption=caption,
            reply_to_message_id=reply_to_message_id,
            disable_notification=disable_notification,
        )

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

    async def get_file(self, file_id: str) -> dict[str, object]:
        """``getFile`` — get file path for downloading."""
        return await self._call("getFile", json_data={"file_id": file_id})

    async def download_file(self, file_path: str, *, timeout: float = 30.0) -> bytes:
        """Download a file by its ``file_path`` from ``getFile`` result."""
        http = self._get_http()
        resp = await http.get(
            f"{self._file_base}/{file_path}",
            timeout=timeout,
            headers=self._host_headers(self._active_idx),
        )
        resp.raise_for_status()
        return resp.content

    async def download_voice(self, file_id: str) -> Path | None:
        """Download a voice/audio file to a local temp path."""
        import tempfile

        try:
            result = await self.get_file(file_id)
            file_path = str(result.get("file_path", ""))
            if not file_path:
                return None
            content = await self.download_file(file_path)
            suffix = ".ogg" if file_path.endswith((".oga", ".ogg")) else (Path(file_path).suffix or ".ogg")
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(content)
            tmp.close()
            return Path(tmp.name)
        except Exception as exc:
            logger.warning("TelegramClient: download_voice failed %s: %s", file_id, exc)
            return None


def get_recommended_send_method(mime_type: str, size: int | None = None) -> str:
    """Recommend the most appropriate Telegram send method based on MIME type and size.

    This helper assists business logic in pre-checking which method to use before sending,
    allowing graceful fallback decisions at a higher layer.

    Args:
        mime_type: MIME type of the media file (e.g., "audio/ogg", "audio/mpeg")
        size: Optional file size in bytes (if known). Used to check size limits.

    Returns:
        Recommended method name: "send_voice", "send_audio", or "send_document"

    Example:
        >>> get_recommended_send_method("audio/ogg", size=1_000_000)
        'send_voice'
        >>> get_recommended_send_method("audio/ogg", size=60_000_000)  # > 50MB
        'send_document'
        >>> get_recommended_send_method("audio/mpeg", size=10_000_000)
        'send_audio'
    """
    from .constants import (
        AUDIO_MIME_TYPES,
        TELEGRAM_VOICE_MAX_SIZE,
        VOICE_MIME_TYPES,
    )

    if size is not None and size > TELEGRAM_VOICE_MAX_SIZE:
        return "send_document"

    if mime_type in VOICE_MIME_TYPES:
        return "send_voice"

    if mime_type in AUDIO_MIME_TYPES:
        return "send_audio"

    return "send_document"
