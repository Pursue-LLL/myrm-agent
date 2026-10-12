"""Discord voice control: opus loading, VoiceManager wiring and the /voice slash command.

[INPUT]
- app.channels.providers.discord.voice.manager::VoiceManager (POS: voice sessions: join / leave, RTP receive, speech-to-text)
- app.channels.providers.discord.voice.player::VoicePlayer (POS: TTS audio playback into a voice client)
- app.channels.types::InboundMessage (POS: channel message value types)

[OUTPUT]
- DiscordVoiceMixin: opus loading, voice manager lifecycle, join / leave / play_audio, voice-input emission and /voice command registration used by DiscordChannel

[POS]
Voice half of DiscordChannel. The host owns the gateway client and the config; the mixin drives the voice subsystem.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord

from app.channels.core.base import BaseChannel
from app.channels.providers.discord.config import (
    DiscordChannelConfig,
)
from app.channels.types import (
    InboundMessage,
)

if TYPE_CHECKING:
    from app.channels.providers.discord.voice.manager import (
        VoiceManager,
    )

logger = logging.getLogger(__name__)


class DiscordVoiceMixin(BaseChannel):
    """Discord voice control for ``DiscordChannel``.

    Requires the host class to provide the attributes below.
    """

    config: DiscordChannelConfig
    _client: discord.Client | None
    _voice_manager: VoiceManager | None
    _command_tree: discord.app_commands.CommandTree | None

    @staticmethod
    def _ensure_opus_loaded() -> None:
        """Ensure libopus is loaded for voice codec support."""
        import discord.opus

        if discord.opus.is_loaded():
            return

        import ctypes.util
        import sys

        opus_path = ctypes.util.find_library("opus")
        if not opus_path and sys.platform == "darwin":
            for candidate in (
                "/opt/homebrew/lib/libopus.dylib",
                "/usr/local/lib/libopus.dylib",
            ):
                import os

                if os.path.isfile(candidate):
                    opus_path = candidate
                    break
        if opus_path:
            try:
                discord.opus.load_opus(opus_path)
                return
            except Exception:
                pass
        if not discord.opus.is_loaded():
            logger.warning(
                "Opus codec not found — voice decoding may fail. "
                "Install libopus: brew install opus (macOS) / apt install libopus0 (Linux)"
            )

    def _init_voice_manager(self) -> None:
        """Initialize the VoiceManager after client is ready."""
        if not self._client or not self.config.voice_enabled:
            return

        self._ensure_opus_loaded()

        from app.channels.providers.discord.voice.manager import (
            VoiceManager,
        )

        self._voice_manager = VoiceManager(
            self._client,
            voice_timeout=self.config.voice_timeout,
            allowed_user_ids=(set(self.config.allowed_users) if self.config.allowed_users else None),
            on_voice_input=self._on_voice_input,
            voice_wake_words=self.config.voice_wake_words,
            voice_barge_in_enabled=self.config.voice_barge_in_enabled,
            follow_user_ids=(set(self.config.voice_follow_users) if self.config.voice_follow_users else None),
            allowed_channels=self.config.voice_allowed_channels or None,
        )

    async def _on_voice_input(
        self,
        chat_id: int,
        user_id: int,
        transcript: str,
        display_name: str,
    ) -> None:
        """Handle transcribed voice input by emitting as InboundMessage."""
        inbound = InboundMessage(
            channel=self.name,
            sender_id=str(user_id),
            sender_name=display_name,
            sent_at=time.time(),
            sent_timezone="UTC",
            chat_id=str(chat_id),
            user_id=str(user_id),
            content=transcript,
            message_id=f"voice-{chat_id}-{int(time.time() * 1000)}",
            metadata={
                "source": "voice",
            },
        )
        await self._emit_inbound(inbound)

    async def join_voice(
        self,
        channel: discord.VoiceChannel,
        *,
        text_channel_id: int = 0,
    ) -> bool:
        """Join a Discord voice channel."""
        if not self._voice_manager:
            return False
        return await self._voice_manager.join(channel, text_channel_id=text_channel_id)

    async def leave_voice(self, guild_id: int) -> None:
        """Leave the voice channel in a guild."""
        if self._voice_manager:
            await self._voice_manager.leave(guild_id)

    async def play_audio(self, guild_id: int, audio_path: str, tts_text: str = "") -> bool:
        """Play audio in the voice channel of a guild."""
        if not self._voice_manager:
            return False

        vc = self._voice_manager.get_voice_client(guild_id)
        receiver = self._voice_manager.get_receiver(guild_id)
        if not vc:
            return False

        from app.channels.providers.discord.voice.player import (
            VoicePlayer,
        )

        player = VoicePlayer(vc, receiver)
        self._voice_manager.register_player(guild_id, player, tts_text)
        try:
            return await player.play(audio_path)
        finally:
            self._voice_manager.unregister_player(guild_id)

    async def _auto_join(self) -> None:
        """Auto-join configured voice channel after bot is ready."""
        channel_id = self.config.voice_auto_join_channel
        if not channel_id or not self._client:
            return
        try:
            ch = self._client.get_channel(int(channel_id))
            if not ch:
                ch = await self._client.fetch_channel(int(channel_id))
            if isinstance(ch, discord.VoiceChannel):
                text_ch_id = int(self.config.voice_text_channel) if self.config.voice_text_channel else 0
                await self.join_voice(ch, text_channel_id=text_ch_id)
                logger.info("Auto-joined voice channel %s", ch.name)
            else:
                logger.warning("Auto-join target %s is not a voice channel", channel_id)
        except Exception as e:
            logger.error("Failed to auto-join voice channel %s: %s", channel_id, e)

    def _register_voice_commands(self) -> None:
        """Register /voice slash commands."""
        if not self._command_tree:
            return

        tree = self._command_tree
        channel_self = self

        @tree.command(name="voice", description="Voice channel controls")
        @discord.app_commands.describe(
            action="join, leave, or status",
            channel="Voice channel to join (for join action)",
        )
        @discord.app_commands.choices(
            action=[
                discord.app_commands.Choice(name="join", value="join"),
                discord.app_commands.Choice(name="leave", value="leave"),
                discord.app_commands.Choice(name="status", value="status"),
            ]
        )
        async def voice_command(
            interaction: discord.Interaction,
            action: str,
            channel: discord.VoiceChannel | None = None,
        ) -> None:
            if not channel_self._voice_manager:
                await interaction.response.send_message("Voice is not enabled.", ephemeral=True)
                return

            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
                return

            if action == "join":
                target = channel
                if not target:
                    member = guild.get_member(interaction.user.id)
                    if member and member.voice and member.voice.channel:
                        target = member.voice.channel  # type: ignore[assignment]
                if not target or not isinstance(target, discord.VoiceChannel):
                    await interaction.response.send_message(
                        "Please specify a voice channel or join one first.",
                        ephemeral=True,
                    )
                    return
                await interaction.response.defer(ephemeral=True)
                text_ch_id = interaction.channel_id or 0
                ok = await channel_self.join_voice(target, text_channel_id=text_ch_id)
                msg = f"Joined **{target.name}**" if ok else "Failed to join voice channel."
                await interaction.followup.send(msg, ephemeral=True)

            elif action == "leave":
                await interaction.response.defer(ephemeral=True)
                await channel_self.leave_voice(guild.id)
                await interaction.followup.send("Left voice channel.", ephemeral=True)

            elif action == "status":
                connected = channel_self._voice_manager.is_connected(guild.id)
                status = "Connected" if connected else "Not connected"
                await interaction.response.send_message(f"Voice status: **{status}**", ephemeral=True)
