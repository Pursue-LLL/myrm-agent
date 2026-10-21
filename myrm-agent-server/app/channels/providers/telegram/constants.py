"""Telegram Bot API constants and limits.

Based on official Telegram Bot API documentation (2026):
https://core.telegram.org/bots/api

[INPUT]
- (none)

[OUTPUT]
- (none)

[POS]
Telegram Bot API constants and limits.
"""

# File size limits (Telegram Bot API restrictions)
TELEGRAM_VOICE_MAX_SIZE = 50 * 1024 * 1024  # 50MB for sendVoice
TELEGRAM_AUDIO_MAX_SIZE = 50 * 1024 * 1024  # 50MB for sendAudio
TELEGRAM_PHOTO_MAX_SIZE = 10 * 1024 * 1024  # 10MB for sendPhoto
TELEGRAM_VIDEO_MAX_SIZE = 50 * 1024 * 1024  # 50MB for sendVideo
TELEGRAM_DOCUMENT_MAX_SIZE = 50 * 1024 * 1024  # 50MB for sendDocument

# MIME types for voice messages (sendVoice)
VOICE_MIME_TYPES = frozenset(
    (
        "audio/ogg",  # OGG with OPUS codec (recommended)
        "audio/opus",  # OPUS codec
    )
)

# MIME types for audio files (sendAudio)
AUDIO_MIME_TYPES = frozenset(
    (
        "audio/mpeg",  # MP3
        "audio/mp4",  # M4A
        "audio/m4a",  # M4A (alternative MIME)
    )
)
