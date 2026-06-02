"""Telegram-specific exceptions for file size validation and API errors.

[INPUT]
- app.channels.core.exceptions::ChannelSendError (POS: Channel exception hierarchy for precise retry and error handling.)

[OUTPUT]
- MediaFileTooLargeError: Base exception for media files exceeding Telegram's size ...
- VoiceMessageTooLargeError: Voice message exceeds Telegram's 50MB sendVoice limit.
- AudioFileTooLargeError: Audio file exceeds Telegram's 50MB sendAudio limit.

[POS]
Telegram-specific exceptions for file size validation and API errors.
"""

from app.channels.core.exceptions import ChannelSendError


class MediaFileTooLargeError(ChannelSendError):
    """Base exception for media files exceeding Telegram's size limits.

    Not retriable — requires fallback to different send method (e.g., sendDocument)
    or file compression.
    """

    def __init__(self, media_type: str, actual_size: int, max_size: int) -> None:
        self.media_type = media_type
        self.actual_size = actual_size
        self.max_size = max_size
        message = (
            f"{media_type} file size {actual_size:,} bytes exceeds "
            f"Telegram limit {max_size:,} bytes. "
            f"Consider sending as document or compressing."
        )
        super().__init__(message, channel="telegram", status_code=413, retriable=False)


class VoiceMessageTooLargeError(MediaFileTooLargeError):
    """Voice message exceeds Telegram's 50MB sendVoice limit.

    Raised when attempting to send voice message (OGG/OPUS) larger than 50MB.
    Business layer should catch and fallback to send_document().
    """

    def __init__(self, actual_size: int, max_size: int = 50 * 1024 * 1024) -> None:
        super().__init__("Voice message", actual_size, max_size)


class AudioFileTooLargeError(MediaFileTooLargeError):
    """Audio file exceeds Telegram's 50MB sendAudio limit.

    Raised when attempting to send audio file (MP3/M4A) larger than 50MB.
    Business layer should catch and fallback to send_document().
    """

    def __init__(self, actual_size: int, max_size: int = 50 * 1024 * 1024) -> None:
        super().__init__("Audio file", actual_size, max_size)
