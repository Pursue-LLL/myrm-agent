"""Discord Voice Player - FFmpeg audio playback with echo prevention.

Plays audio files in Discord voice channels via FFmpeg PCM streaming.
Coordinates with VoiceReceiver to pause capture during playback,
preventing the bot from hearing its own output.

[INPUT]
- discord.VoiceClient (POS: Discord voice connection)
- VoiceReceiver (POS: for echo prevention pause/resume)

[OUTPUT]
- VoicePlayer: class - audio playback in voice channels

[POS]
Voice audio output. Uses FFmpeg for format conversion and
discord.py's built-in AudioSource pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import discord

from app.channels.providers.discord.voice.receiver import (
    VoiceReceiver,
)

logger = logging.getLogger(__name__)

_PLAYBACK_TIMEOUT = 120


class VoicePlayer:
    """Plays audio in a Discord voice channel with echo prevention.

    Pauses the VoiceReceiver during playback so the bot does not
    capture its own TTS output.
    """

    def __init__(
        self,
        voice_client: discord.VoiceClient,
        receiver: VoiceReceiver | None = None,
    ) -> None:
        self._vc = voice_client
        self._receiver = receiver
        self._playing = False

    @property
    def is_playing(self) -> bool:
        return self._playing

    async def play(self, audio_path: str | Path) -> bool:
        """Play an audio file in the voice channel.

        Args:
            audio_path: Path to the audio file (any FFmpeg-supported format).

        Returns:
            True if playback completed successfully.
        """
        path = Path(audio_path)
        if not path.exists():
            logger.error("Audio file not found: %s", path)
            return False

        if not self._vc.is_connected():
            logger.warning("Cannot play - not connected to voice channel")
            return False

        if self._vc.is_playing():
            self._vc.stop()

        if self._receiver:
            self._receiver.pause()

        self._playing = True
        done_event = asyncio.Event()

        def after_playback(error: Exception | None) -> None:
            if error:
                logger.error("Playback error: %s", error)
            self._playing = False
            done_event.set()

        try:
            source = discord.FFmpegPCMAudio(str(path))
            self._vc.play(source, after=after_playback)

            try:
                await asyncio.wait_for(done_event.wait(), timeout=_PLAYBACK_TIMEOUT)
            except TimeoutError:
                logger.warning("Playback timeout after %ds", _PLAYBACK_TIMEOUT)
                self._vc.stop()
                self._playing = False
                return False
            finally:
                if self._receiver:
                    self._receiver.resume()

        except Exception as e:
            logger.error("Failed to play audio: %s", e)
            self._playing = False
            if self._receiver:
                self._receiver.resume()
            return False

        return True

    def stop(self) -> None:
        """Stop current playback immediately."""
        if self._vc.is_playing():
            self._vc.stop()
        self._playing = False
        if self._receiver:
            self._receiver.resume()
