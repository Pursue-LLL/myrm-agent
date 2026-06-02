"""Discord Voice Channel support.

Provides voice receive, playback, and lifecycle management for
Discord voice channels. Requires discord.py[voice] and PyNaCl.
"""

from app.channels.providers.discord.voice.manager import (
    VoiceManager,
)
from app.channels.providers.discord.voice.player import (
    VoicePlayer,
)
from app.channels.providers.discord.voice.receiver import (
    VoiceReceiver,
)

__all__ = ["VoiceManager", "VoicePlayer", "VoiceReceiver"]
