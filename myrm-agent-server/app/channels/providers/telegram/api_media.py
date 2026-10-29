"""Telegram media methods: sending photos, documents, voice, audio and video, and downloading files.

[INPUT]
- telegram.api_core::TelegramApiBase (POS: Bot API transport: endpoint, pooled HTTP client, unified ``_call``)

[OUTPUT]
- TelegramMediaApi: photo, document, voice, audio and video sending, file download
- get_recommended_send_method: the send method a MIME type and size call for

[POS]
Media group of the Telegram Bot API client: uploads go through one ``_send_media``, downloads through ``getFile``.
``TelegramClient`` inherits the group.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .api_core import TelegramApiBase

logger = logging.getLogger(__name__)

_UPLOAD_TIMEOUT = 60.0


class TelegramMediaApi(TelegramApiBase):
    """Send media and download files through the Bot API."""

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

    async def get_file(self, file_id: str) -> dict[str, object]:
        """``getFile`` — get file path for downloading."""
        return await self._call("getFile", json_data={"file_id": file_id})

    async def download_file(self, file_path: str, *, timeout: float = 30.0) -> bytes:
        """Download a file by its ``file_path`` from ``getFile`` result."""
        http = self._get_http()
        resp = await http.get(f"{self._file_base}/{file_path}", timeout=timeout)
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

    async def download_video(self, file_id: str) -> Path | None:
        """Download a video/video_note file to a local temp path for STT."""
        import tempfile

        try:
            result = await self.get_file(file_id)
            file_path = str(result.get("file_path", ""))
            if not file_path:
                return None
            content = await self.download_file(file_path)
            suffix = Path(file_path).suffix or ".mp4"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.write(content)
            tmp.close()
            return Path(tmp.name)
        except Exception as exc:
            logger.warning("TelegramClient: download_video failed %s: %s", file_id, exc)
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
