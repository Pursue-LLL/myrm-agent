"""Discord Voice Manager - lifecycle, per-guild state, auto-timeout, follow-user.

Manages voice connections across multiple guilds. Each guild has
independent state (VoiceClient, VoiceReceiver, listen loop).
Auto-timeout disconnects the bot when no speech is detected.
Follow-user delegates to VoiceFollowManager for user tracking.
A speaker is transcribed only when the speaker gate admits them.

[INPUT]
- discord.Client (POS: Discord bot client)
- VoiceReceiver (POS: RTP packet capture)
- VoicePlayer (POS: audio playback)
- VoiceInputPipeline (POS: one utterance from PCM to the agent, or dropped)

[OUTPUT]
- VoiceManager: class - voice lifecycle manager
- VoiceSpeakerGate: type alias - (text channel id, user id) -> whether the access policy admits the speaker

[POS]
High-level voice orchestration. Owns per-guild state and
coordinates receiver/player lifecycle with follow-user support;
each finished utterance from an admitted speaker is handed to the input pipeline; a refused speaker's audio
never reaches speech-to-text, and with no gate wired no speaker is admitted.
Leaving every guild is concurrent, so one guild that waits for
the gateway's confirmation does not hold up the others. A join over a
state whose VoiceClient discord.py has dropped releases that state first;
over one discord.py is still reconnecting, the join is declined.
A leave disconnects the VoiceClient for as long as discord.py holds it, connected or not. The utterances finished in
one poll keep the text-channel binding they were admitted under; a join that binds the session to another
text channel drops the speech the receiver has not yet delivered.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Set
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import discord

from app.channels.providers.discord.voice.follow import (
    VoiceFollowManager,
    VoiceTarget,
)
from app.channels.providers.discord.voice.input_pipeline import (
    VoiceInputCallback,
    VoiceInputPipeline,
)
from app.channels.providers.discord.voice.receiver import (
    VoiceReceiver,
)

if TYPE_CHECKING:
    from app.channels.providers.discord.voice.player import VoicePlayer

logger = logging.getLogger(__name__)

VoiceSpeakerGate = Callable[[int, int], Awaitable[bool]]

_KEEPALIVE_INTERVAL = 15
_LISTEN_POLL_INTERVAL = 0.2


@dataclass
class _GuildVoiceState:
    """Per-guild voice connection state."""

    voice_client: discord.VoiceClient
    receiver: VoiceReceiver
    text_channel_id: int = 0
    listen_task: asyncio.Task[None] | None = None
    joined_at: float = field(default_factory=time.monotonic)
    last_speech_at: float = field(default_factory=time.monotonic)
    refused_speakers: set[int] = field(default_factory=set)

    @property
    def held_by_discord(self) -> bool:
        """Whether discord.py still registers this VoiceClient on its guild: connected, or being brought back up."""
        return self.voice_client.guild.voice_client is self.voice_client


class VoiceManager:
    """Manages Discord voice connections across guilds.

    Provides join/leave lifecycle, auto-timeout, listen loops that hand
    each utterance to the input pipeline, and follow-user delegation.
    """

    def __init__(
        self,
        client: discord.Client,
        *,
        voice_timeout: int = 300,
        allowed_user_ids: Set[str] | None = None,
        on_voice_input: VoiceInputCallback | None = None,
        speaker_gate: VoiceSpeakerGate | None = None,
        voice_wake_words: list[str] | None = None,
        voice_barge_in_enabled: bool = False,
        follow_user_ids: Set[str] | None = None,
        allowed_channels: list[tuple[str, str]] | None = None,
    ) -> None:
        self._client = client
        self._voice_timeout = voice_timeout
        self._allowed_user_ids: set[str] = set(allowed_user_ids) if allowed_user_ids else set()
        self._speaker_gate = speaker_gate

        self._guilds: dict[int, _GuildVoiceState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

        self._input = VoiceInputPipeline(
            client,
            on_voice_input=on_voice_input,
            wake_words=voice_wake_words,
            barge_in_enabled=voice_barge_in_enabled,
        )

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

    def register_player(self, guild_id: int, player: VoicePlayer, text: str = "") -> None:
        """Register the currently active VoicePlayer and the text it is playing."""
        self._input.register_player(guild_id, player, text)

    def unregister_player(self, guild_id: int) -> None:
        """Unregister the player once playback completes."""
        self._input.unregister_player(guild_id)

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

    @staticmethod
    def _bind_text_channel(guild_id: int, state: _GuildVoiceState, text_channel_id: int) -> None:
        """Bind the session to ``text_channel_id`` (0 keeps the binding); a different one drops the undelivered speech.

        What the receiver still buffers was said for the conversation it was captured under; the next poll would
        deliver it into the new one.
        """
        if not text_channel_id or text_channel_id == state.text_channel_id:
            return
        state.receiver.discard_pending()
        state.text_channel_id = text_channel_id
        logger.info("Voice session in guild %d bound to text channel %d, receiver buffers cleared", guild_id, text_channel_id)

    async def join(
        self,
        channel: VoiceTarget,
        *,
        text_channel_id: int = 0,
    ) -> bool:
        """Join a voice channel and start listening."""
        guild_id = channel.guild.id

        async with self._guild_lock(guild_id):
            state = self._guilds.get(guild_id)
            if state and state.voice_client.is_connected():
                if state.voice_client.channel and state.voice_client.channel.id == channel.id:
                    self._bind_text_channel(guild_id, state, text_channel_id)
                    return True
                await state.voice_client.move_to(channel)
                self._bind_text_channel(guild_id, state, text_channel_id)
                return True

            if state:
                if state.held_by_discord:
                    # discord.py still holds this VoiceClient and is bringing it back up: it would refuse a join
                    # now, and releasing the session would cut that reconnect short.
                    logger.debug("Voice session in guild %d is reconnecting, join declined", guild_id)
                    return False
                # discord.py dropped the VoiceClient without an event that removes the state; its listen loop
                # must not outlive it, or its voice timeout would leave this guild by id and end the new session.
                del self._guilds[guild_id]
                await self._release(state)

            try:
                vc: discord.VoiceClient = await channel.connect(timeout=10.0)
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
            await self._release(state)

        logger.info("Left voice channel in guild %d", guild_id)

    async def _release(self, state: _GuildVoiceState) -> None:
        """Stop a session's listen loop and receiver, and disconnect its VoiceClient unless discord.py dropped it."""
        if state.listen_task and not state.listen_task.done():
            state.listen_task.cancel()
            try:
                await state.listen_task
            except asyncio.CancelledError:
                pass

        state.receiver.stop()

        # A VoiceClient discord.py is bringing back up is not connected yet but stays registered on the guild, and
        # only a disconnect clears that; until then discord.py refuses every join. One it has dropped must be left
        # alone: its disconnect waits for a confirmation that never arrives.
        if state.voice_client.is_connected() or state.held_by_discord:
            await state.voice_client.disconnect(force=True)

    async def leave_all(self) -> None:
        """Disconnect from all voice channels and stop reconciliation.

        The guilds leave concurrently: discord.py waits for a gateway event that confirms each leave, so a guild
        that waits it out must not hold up the others, and a caller that gives up on the whole leave still has
        every guild's leave under way.
        """
        await self._follow.destroy()
        guild_ids = list(self._guilds)
        results = await asyncio.gather(*(self.leave(gid) for gid in guild_ids), return_exceptions=True)
        for gid, result in zip(guild_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("Failed to leave voice in guild %d: %r", gid, result)

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

        bot_user = self._client.user
        if bot_user is not None and member.id == bot_user.id:
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

    async def _speaker_admitted(self, guild_id: int, state: _GuildVoiceState, text_channel_id: int, user_id: int) -> bool:
        """Whether the speaker gate admits this speaker; asked for every utterance, before it is transcribed.

        The first refusal of a speaker in a session is logged, so an owner whose own speech is ignored can find out why.
        """
        if self._speaker_gate is not None and await self._speaker_gate(text_channel_id or guild_id, user_id):
            return True
        if user_id not in state.refused_speakers:
            state.refused_speakers.add(user_id)
            logger.warning(
                "Voice speaker %d in guild %d is not admitted by the access policy; their speech is not transcribed",
                user_id,
                guild_id,
            )
        return False

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
                # Transcribing one utterance takes seconds, during which /voice join can rebind the session to
                # another text channel; every utterance of this batch is admitted and routed under one binding.
                text_channel_id = state.text_channel_id
                for user_id, pcm_data in completed:
                    if self._allowed_user_ids and str(user_id) not in self._allowed_user_ids:
                        continue
                    if not await self._speaker_admitted(guild_id, state, text_channel_id, user_id):
                        continue
                    state.last_speech_at = time.monotonic()
                    await self._input.process(guild_id, user_id, pcm_data, text_channel_id)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Voice listen loop error in guild %d: %s", guild_id, e, exc_info=True)
