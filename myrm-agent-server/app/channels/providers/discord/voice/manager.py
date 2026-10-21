"""Discord Voice Manager - lifecycle, per-guild state, auto-timeout, follow-user.

Manages voice connections across multiple guilds. Each guild has
independent state (VoiceClient, VoiceReceiver, listen loop).
Auto-timeout disconnects the bot when no speech is detected.
Follow-user delegates to VoiceFollowManager for user tracking.

[INPUT]
- discord.Client (POS: Discord bot client)
- VoiceReceiver (POS: RTP packet capture)
- VoicePlayer (POS: audio playback)

[OUTPUT]
- VoiceManager: class - voice lifecycle manager

[POS]
High-level voice orchestration. Owns per-guild state and
coordinates receiver/player lifecycle with follow-user support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Set
from dataclasses import dataclass, field

import discord

from app.channels.providers.discord.voice.follow import (
    VoiceFollowManager,
)
from app.channels.providers.discord.voice.receiver import (
    VoiceReceiver,
)

logger = logging.getLogger(__name__)

_KEEPALIVE_INTERVAL = 15
_LISTEN_POLL_INTERVAL = 0.2

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


@dataclass
class _GuildVoiceState:
    """Per-guild voice connection state."""

    voice_client: discord.VoiceClient
    receiver: VoiceReceiver
    text_channel_id: int = 0
    listen_task: asyncio.Task[None] | None = None
    joined_at: float = field(default_factory=time.monotonic)
    last_speech_at: float = field(default_factory=time.monotonic)


VoiceInputCallback = Callable[[int, int, str, str], Awaitable[None]]


class VoiceManager:
    """Manages Discord voice connections across guilds.

    Provides join/leave lifecycle, auto-timeout, listen loops,
    speech-to-text processing, and follow-user delegation.
    """

    def __init__(
        self,
        client: discord.Client,
        *,
        voice_timeout: int = 300,
        allowed_user_ids: Set[str] | None = None,
        on_voice_input: VoiceInputCallback | None = None,
        voice_wake_words: list[str] | None = None,
        voice_barge_in_enabled: bool = False,
        follow_user_ids: Set[str] | None = None,
        allowed_channels: list[tuple[str, str]] | None = None,
    ) -> None:
        self._client = client
        self._voice_timeout = voice_timeout
        self._allowed_user_ids: set[str] = set(allowed_user_ids) if allowed_user_ids else set()
        self._on_voice_input = on_voice_input
        self._voice_wake_words = [w.lower() for w in (voice_wake_words or [])]
        self._voice_barge_in_enabled = voice_barge_in_enabled

        self._guilds: dict[int, _GuildVoiceState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

        self._active_players: dict[int, object] = {}
        self._active_play_texts: dict[int, str] = {}
        self._wake_until: dict[int, float] = {}

        self._follow = VoiceFollowManager(
            client,
            self,
            follow_user_ids=follow_user_ids,
            allowed_channels=allowed_channels,
            on_guild_leave_check=self._should_leave_guild,
        )

    @property
    def follow_enabled(self) -> bool:
        return self._follow.enabled

    async def start_reconciliation(self) -> None:
        await self._follow.start_reconciliation()

    def register_player(self, guild_id: int, player: object, text: str = "") -> None:
        """Register the currently active VoicePlayer and the text it is playing."""
        self._active_players[guild_id] = player
        self._active_play_texts[guild_id] = text

    def unregister_player(self, guild_id: int) -> None:
        """Unregister the player once playback completes."""
        self._active_players.pop(guild_id, None)
        self._active_play_texts.pop(guild_id, None)

    @property
    def active_guilds(self) -> list[int]:
        return list(self._guilds.keys())

    def is_connected(self, guild_id: int) -> bool:
        state = self._guilds.get(guild_id)
        return state is not None and state.voice_client.is_connected()

    def _guild_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    async def join(
        self,
        channel: discord.VoiceChannel,
        *,
        text_channel_id: int = 0,
    ) -> bool:
        """Join a voice channel and start listening."""
        guild_id = channel.guild.id

        async with self._guild_lock(guild_id):
            if guild_id in self._guilds:
                state = self._guilds[guild_id]
                if state.voice_client.is_connected():
                    if state.voice_client.channel and state.voice_client.channel.id == channel.id:
                        if text_channel_id:
                            state.text_channel_id = text_channel_id
                        return True
                    await state.voice_client.move_to(channel)
                    if text_channel_id:
                        state.text_channel_id = text_channel_id
                    return True

            try:
                vc = await channel.connect(timeout=10.0)
            except Exception as e:
                logger.error("Failed to join voice channel %s: %s", channel.id, e)
                return False

            receiver = VoiceReceiver(vc, allowed_user_ids=self._allowed_user_ids)
            receiver.start()

            state = _GuildVoiceState(
                voice_client=vc,
                receiver=receiver,
                text_channel_id=text_channel_id,
            )
            self._guilds[guild_id] = state

            state.listen_task = asyncio.get_running_loop().create_task(
                self._listen_loop(guild_id),
                name=f"voice-listen-{guild_id}",
            )

        logger.info("Joined voice channel %s in guild %d", channel.name, guild_id)
        return True

    async def leave(self, guild_id: int) -> None:
        """Leave voice channel and clean up state."""
        async with self._guild_lock(guild_id):
            state = self._guilds.pop(guild_id, None)
            if not state:
                return

            if state.listen_task and not state.listen_task.done():
                state.listen_task.cancel()
                try:
                    await state.listen_task
                except asyncio.CancelledError:
                    pass

            state.receiver.stop()

            if state.voice_client.is_connected():
                await state.voice_client.disconnect(force=True)

        logger.info("Left voice channel in guild %d", guild_id)

    async def leave_all(self) -> None:
        """Disconnect from all voice channels and stop reconciliation."""
        await self._follow.destroy()
        guild_ids = list(self._guilds.keys())
        for gid in guild_ids:
            await self.leave(gid)

    def get_voice_client(self, guild_id: int) -> discord.VoiceClient | None:
        state = self._guilds.get(guild_id)
        return state.voice_client if state else None

    def get_receiver(self, guild_id: int) -> VoiceReceiver | None:
        state = self._guilds.get(guild_id)
        return state.receiver if state else None

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice state changes - follow-user + auto-disconnect when alone."""
        guild_id = member.guild.id

        if member.id == self._client.user.id:
            await self._handle_bot_voice_update(member, before, after)
            return

        if self._follow.enabled and self._follow.is_followed_user(str(member.id)):
            await self._follow.handle_followed_user_update(member, before, after)
            return

        state = self._guilds.get(guild_id)
        if not state or not state.voice_client.is_connected():
            return
        bot_channel = state.voice_client.channel
        if not bot_channel:
            return
        non_bot_members = [m for m in bot_channel.members if not m.bot]
        if not non_bot_members and guild_id not in self._follow.followed_guilds:
            logger.info("All users left voice channel in guild %d, disconnecting", guild_id)
            await self.leave(guild_id)

    async def _handle_bot_voice_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle when the bot itself is moved or disconnected by an admin."""
        guild_id = member.guild.id

        if not after.channel and before.channel:
            async with self._guild_lock(guild_id):
                state = self._guilds.pop(guild_id, None)
                if state:
                    if state.listen_task and not state.listen_task.done():
                        state.listen_task.cancel()
                    state.receiver.stop()
            logger.info("Bot was disconnected from voice in guild %d", guild_id)

        await self._follow.handle_bot_voice_update(guild_id, before.channel, after.channel)

    async def _should_leave_guild(self, guild_id: int) -> bool:
        """Check if bot should leave: True when no non-bot members remain."""
        state = self._guilds.get(guild_id)
        if not state:
            return False
        bot_channel = state.voice_client.channel
        if not bot_channel:
            return True
        non_bot = [m for m in bot_channel.members if not m.bot]
        return not non_bot

    async def _listen_loop(self, guild_id: int) -> None:
        """Poll for completed utterances and process them via STT."""
        state = self._guilds.get(guild_id)
        if not state:
            return

        last_keepalive = time.monotonic()
        try:
            while state.receiver.running:
                await asyncio.sleep(_LISTEN_POLL_INTERVAL)

                now = time.monotonic()
                if now - last_keepalive >= _KEEPALIVE_INTERVAL:
                    last_keepalive = now
                    try:
                        if state.voice_client.is_connected():
                            state.voice_client.send_audio_packet(b"\xf8\xff\xfe", encode=False)
                    except Exception:
                        pass

                if self._voice_timeout > 0:
                    if now - state.last_speech_at > self._voice_timeout:
                        logger.info(
                            "Voice timeout in guild %d (%ds)",
                            guild_id,
                            self._voice_timeout,
                        )
                        await self.leave(guild_id)
                        return

                completed = state.receiver.check_silence()
                for user_id, pcm_data in completed:
                    if self._allowed_user_ids and str(user_id) not in self._allowed_user_ids:
                        continue
                    state.last_speech_at = time.monotonic()
                    await self._process_voice_input(guild_id, user_id, pcm_data, state.text_channel_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Voice listen loop error in guild %d: %s", guild_id, e, exc_info=True)

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

    async def _process_voice_input(
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

            if self._voice_barge_in_enabled:
                if self._handle_barge_in(guild_id, transcript, transcript_lower):
                    return

            if self._voice_wake_words:
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
            import difflib
            import re

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
        import re

        now = time.time()
        is_awake = self._wake_until.get(guild_id, 0) > now

        woke_up = False
        for w in self._voice_wake_words:
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
