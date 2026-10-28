"""Telegram Bot API constants and limits.

Based on official Telegram Bot API documentation (2026):
https://core.telegram.org/bots/api

[INPUT]
- app.channels.types::reaction_key (POS: canonical reaction glyph form)

[OUTPUT]
- TELEGRAM_REACTION_EMOJI: the emoji a bot may set as a message reaction

[POS]
Telegram Bot API constants and limits.
"""

from app.channels.types import reaction_key

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

# Reaction emoji Telegram accepts on a message (``ReactionTypeEmoji`` in the Bot API); any other
# value is rejected with REACTION_INVALID. Kept in ``reaction_key`` form, like the capability set.
_PLAIN_REACTION_EMOJI = (
    "❤ 👍 👎 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 "
    "👌 🕊 🤡 🥱 🥴 😍 🐳 🌚 🌭 💯 🤣 ⚡ 🍌 🏆 💔 🤨 😐 "
    "🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 "
    "🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 🙉 🦄 😘 💊 🙊 😎 👾 🤷 "
    "😡"
).split()
# The four zero-width-joiner sequences are spelled out so the invisible joiner survives editing.
_JOINED_REACTION_EMOJI = (
    "\u2764\u200d\U0001f525",
    "\U0001f468\u200d\U0001f4bb",
    "\U0001f937\u200d\u2642",
    "\U0001f937\u200d\u2640",
)

TELEGRAM_REACTION_EMOJI = frozenset(reaction_key(glyph) for glyph in (*_PLAIN_REACTION_EMOJI, *_JOINED_REACTION_EMOJI))
