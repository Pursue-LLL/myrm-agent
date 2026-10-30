"""Discord Voice Input Pipeline - one utterance from PCM to the agent, or dropped.

An utterance goes PCM -> WAV -> speech-to-text, then past the hallucination
filter, the echo/barge-in check and the wake-word gate, and reaches the
voice-input callback with the speaker's display name.

[INPUT]
- discord.Client (POS: Discord bot client; resolves display names from guild membership)
- VoiceReceiver (POS: RTP packet capture; converts PCM to WAV)
- VoicePlayer (POS: audio playback; stopped on barge-in)
- app.channels.voice.stt::transcribe (POS: speech-to-text)

[OUTPUT]
- VoiceInputPipeline: class - per-manager utterance processing and playback registry
- VoiceInputCallback: type alias - (text channel id, user id, transcript, display name)

[POS]
The speech-input gate of the voice manager. Owns what only this gate needs:
the playback registry that echo detection compares against and each guild's
wake-up window. Lifecycle and connections stay in the manager.
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from app.channels.providers.discord.voice.receiver import (
    VoiceReceiver,
)

if TYPE_CHECKING:
    from app.channels.providers.discord.voice.player import VoicePlayer

logger = logging.getLogger(__name__)

VoiceInputCallback = Callable[[int, int, str, str], Awaitable[None]]

_WHISPER_HALLUCINATIONS = frozenset(
    {
        "thanks for watching",
        "thank you for watching",
        "thank you",
        "thanks for watching!",
        "thank you for watching!",
        "you",
        "",
        "...",
        "bye",
        "bye bye",
        "bye.",
        "the end",
        "the end.",
        "subtitles by the amara.org community",
        "subtitle by the amara.org community",
    }
)


def _is_whisper_hallucination(text: str) -> bool:
    """Filter common Whisper hallucinations from silence."""
    return text.strip().lower() in _WHISPER_HALLUCINATIONS


class VoiceInputPipeline:
    """Turns the finished utterances of a manager's guilds into transcripts for the agent."""

    def __init__(
        self,
        client: discord.Client,
        *,
        on_voice_input: VoiceInputCallback | None = None,
        wake_words: list[str] | None = None,
        barge_in_enabled: bool = False,
    ) -> None:
        self._client = client
        self._on_voice_input = on_voice_input
        self._wake_words = [w.lower() for w in (wake_words or [])]
        self._barge_in_enabled = barge_in_enabled

        self._active_players: dict[int, VoicePlayer] = {}
        self._active_play_texts: dict[int, str] = {}
        self._wake_until: dict[int, float] = {}

    def register_player(self, guild_id: int, player: VoicePlayer, text: str = "") -> None:
        """Register the currently active VoicePlayer and the text it is playing."""
        self._active_players[guild_id] = player
        self._active_play_texts[guild_id] = text

    def unregister_player(self, guild_id: int) -> None:
        """Unregister the player once playback completes."""
        self._active_players.pop(guild_id, None)
        self._active_play_texts.pop(guild_id, None)

    def _resolve_display_name(self, guild_id: int, user_id: int) -> str:
        """Resolve a user's display name from guild membership."""
        try:
            guild = self._client.get_guild(guild_id)
            if guild:
                member = guild.get_member(user_id)
                if member:
                    return member.display_name
        except Exception:
            pass
        return str(user_id)

    async def process(
        self,
        guild_id: int,
        user_id: int,
        pcm_data: bytes,
        text_channel_id: int,
    ) -> None:
        """Convert PCM -> WAV -> STT -> callback."""
        try:
            wav_bytes = await asyncio.to_thread(VoiceReceiver.pcm_to_wav_bytes, pcm_data)

            from app.channels.types import VoiceConfig
            from app.channels.voice.stt import transcribe

            vc = VoiceConfig(stt_enabled=True)
            result = await transcribe(None, vc, audio_bytes=wav_bytes)
            if not result or not result.text:
                return

            transcript = result.text.strip()
            if not transcript or _is_whisper_hallucination(transcript):
                return

            transcript_lower = transcript.lower()

            if self._barge_in_enabled:
                if self._handle_barge_in(guild_id, transcript, transcript_lower):
                    return

            if self._wake_words:
                if not self._check_wake_word(guild_id, transcript_lower):
                    return

            display_name = self._resolve_display_name(guild_id, user_id)
            logger.info(
                "Voice input from %s (%d) in guild %d: %s",
                display_name,
                user_id,
                guild_id,
                transcript[:100],
            )

            if self._on_voice_input:
                await self._on_voice_input(
                    text_channel_id or guild_id,
                    user_id,
                    transcript,
                    display_name,
                )

        except Exception as e:
            logger.warning("Voice input processing failed: %s", e, exc_info=True)

    def _handle_barge_in(self, guild_id: int, transcript: str, transcript_lower: str) -> bool:
        """Check for echo/barge-in. Returns True if input should be discarded."""
        player = self._active_players.get(guild_id)
        if not player or not getattr(player, "is_playing", False):
            return False

        playback_text = self._active_play_texts.get(guild_id, "")
        if playback_text:
            clean_transcript = re.sub(r"[^\w\s]", "", transcript_lower).strip()
            clean_playback = re.sub(r"[^\w\s]", "", playback_text.lower()).strip()

            if clean_transcript and clean_playback:
                match = difflib.SequenceMatcher(None, clean_transcript, clean_playback).find_longest_match(
                    0, len(clean_transcript), 0, len(clean_playback)
                )

                if match.size / len(clean_transcript) > 0.8:
                    logger.info(
                        "Voice input discarded as echo (match=%.0f%%): %s",
                        match.size / len(clean_transcript) * 100,
                        transcript,
                    )
                    return True

        logger.info("Barge-in detected! Stopping playback. User said: %s", transcript)
        try:
            player.stop()
        except Exception as e:
            logger.error("Failed to stop player on barge-in: %s", e)
        return False

    def _check_wake_word(self, guild_id: int, transcript_lower: str) -> bool:
        """Check wake word activation. Returns True if input should be processed."""
        now = time.time()
        is_awake = self._wake_until.get(guild_id, 0) > now

        woke_up = False
        for w in self._wake_words:
            is_ascii = all(ord(c) < 128 for c in w)
            if is_ascii:
                if re.search(r"\b" + re.escape(w) + r"\b", transcript_lower):
                    woke_up = True
                    break
            elif w in transcript_lower:
                woke_up = True
                break

        if not is_awake and not woke_up:
            logger.debug("Voice input discarded (asleep): %s", transcript_lower)
            return False

        self._wake_until[guild_id] = now + 30.0
        return True
