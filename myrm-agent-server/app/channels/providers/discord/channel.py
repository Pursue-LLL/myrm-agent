"""Discord channel implementation.

Supports two modes via `config.enable_gateway`:
- True (Standalone): Starts a discord.py Client to listen for WebSocket events.
- False (SaaS): Only uses REST API, relies on external webhook for inbound.

Voice channel support is enabled via `config.voice_enabled`. When active,
the bot can join voice channels, listen via RTP, transcribe speech (STT),
and play back TTS audio.

[INPUT]
- app.channels.providers.discord.inbound::DiscordInboundMixin (POS: gateway event parsing and history reads)
- app.channels.providers.discord.outbound::DiscordOutboundMixin (POS: REST sending, forum threads and message maintenance)
- app.channels.providers.discord.voice_control::DiscordVoiceMixin (POS: opus loading, VoiceManager wiring and the /voice slash command)
- app.channels.types::ChannelCapabilities (POS: Provides ArtifactInfo, infer_language, infer_artifact_type. ReplyContext for structured reply/quote context.)
- app.channels.types.messages::ReasoningDisplay, RenderStyle, ToolSummaryDisplay (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)
- app.channels.core.base::BaseChannel (POS: Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. Supports outbound (send) and inbound (on_inbound callback) bidirectional communication. Providers may declare credential_spec and from_credentials for self-contained credential management.)

[OUTPUT]
- DiscordChannel: Discord channel provider (credentials, capabilities, gateway lifecycle and health); event parsing, sending and voice come from the mixins.

[POS]
Discord channel implementation with Forum channel support.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, ClassVar, Self

import discord

from app.channels.core.allow_policy import (
    AllowPolicy,
    ChatPolicy,
)
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import (
    credential_field,
    credential_spec,
)
from app.channels.providers.discord.config import (
    DiscordChannelConfig,
)
from app.channels.providers.discord.inbound import DiscordInboundMixin
from app.channels.providers.discord.outbound import DiscordOutboundMixin
from app.channels.providers.discord.voice_control import DiscordVoiceMixin
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
)
from app.channels.types.messages import (
    ReasoningDisplay,
    RenderStyle,
    ToolSummaryDisplay,
)

if TYPE_CHECKING:
    from app.channels.providers.discord.voice.manager import (
        VoiceManager,
    )

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 2000


_HEALTH_PROBE_TIMEOUT = 10.0


class DiscordChannel(DiscordInboundMixin, DiscordOutboundMixin, DiscordVoiceMixin, BaseChannel):
    """Discord channel provider.

    Uses discord.py Client for both Gateway (inbound) and REST (outbound).
    When enable_gateway=False, only REST sending works (no inbound).
    """

    name = "discord"
    render_style = RenderStyle(
        format="markdown",
        max_text_length=MAX_TEXT_LENGTH,
        reasoning_display=ReasoningDisplay.COLLAPSED,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )
    credential_spec = credential_spec(
        "discordCredentials",
        bot_token=credential_field("botToken", "DISCORD_BOT_TOKEN"),
        enable_gateway=credential_field("enableGateway", "DISCORD_ENABLE_GATEWAY", default="true"),
        allowed_users=credential_field("allowedUsers", "DISCORD_ALLOWED_USERS", default=""),
        allowed_guilds=credential_field("allowedGuilds", "DISCORD_ALLOWED_GUILDS", default=""),
        bot_policy=credential_field("botPolicy", "DISCORD_BOT_POLICY", default="deny"),
        voice_enabled=credential_field("voiceEnabled", "DISCORD_VOICE_ENABLED", default="false"),
        voice_barge_in_enabled=credential_field("voiceBargeInEnabled", "DISCORD_VOICE_BARGE_IN_ENABLED", default="false"),
        voice_wake_words=credential_field("voiceWakeWords", "DISCORD_VOICE_WAKE_WORDS", default=""),
        voice_timeout=credential_field("voiceTimeout", "DISCORD_VOICE_TIMEOUT", default="300"),
        auto_thread=credential_field("autoThread", "DISCORD_AUTO_THREAD", default="true"),
        no_thread_channels=credential_field("noThreadChannels", "DISCORD_NO_THREAD_CHANNELS", default=""),
        voice_auto_join_channel=credential_field("voiceAutoJoinChannel", "DISCORD_VOICE_AUTO_JOIN_CHANNEL", default=""),
        voice_text_channel=credential_field("voiceTextChannel", "DISCORD_VOICE_TEXT_CHANNEL", default=""),
        voice_follow_users=credential_field("voiceFollowUsers", "DISCORD_VOICE_FOLLOW_USERS", default=""),
        voice_allowed_channels=credential_field("voiceAllowedChannels", "DISCORD_VOICE_ALLOWED_CHANNELS", default=""),
    )

    _BOT_POLICY_MAP: ClassVar[dict[str, ChatPolicy]] = {
        "deny": ChatPolicy.DENY,
        "mention_only": ChatPolicy.MENTION_ONLY,
        "allow": ChatPolicy.ALLOW,
    }

    @classmethod
    def from_credentials(cls, credentials: dict[str, str]) -> Self:
        """Create channel from resolved credentials."""
        enable_gateway = str(credentials.get("enable_gateway", "true")).lower() in (
            "true",
            "1",
            "yes",
        )
        allowed_users_str = credentials.get("allowed_users", "")
        allowed_users = [u.strip() for u in allowed_users_str.split(",") if u.strip()] if allowed_users_str else []
        allowed_guilds_str = credentials.get("allowed_guilds", "")
        allowed_guilds = [g.strip() for g in allowed_guilds_str.split(",") if g.strip()] if allowed_guilds_str else []

        auto_thread = str(credentials.get("auto_thread", "true")).lower() in (
            "true",
            "1",
            "yes",
        )
        no_thread_channels_str = credentials.get("no_thread_channels", "")
        no_thread_channels = (
            [ch.strip() for ch in no_thread_channels_str.split(",") if ch.strip()] if no_thread_channels_str else []
        )

        voice_enabled = str(credentials.get("voice_enabled", "false")).lower() in (
            "true",
            "1",
            "yes",
        )
        voice_barge_in_enabled = str(credentials.get("voice_barge_in_enabled", "false")).lower() in (
            "true",
            "1",
            "yes",
        )
        voice_wake_words_str = credentials.get("voice_wake_words", "")
        voice_wake_words = [w.strip() for w in voice_wake_words_str.split(",") if w.strip()] if voice_wake_words_str else []
        voice_timeout_str = credentials.get("voice_timeout", "300")
        voice_timeout = int(voice_timeout_str) if voice_timeout_str.isdigit() else 300
        voice_auto_join = credentials.get("voice_auto_join_channel", "") or None
        voice_text_channel = credentials.get("voice_text_channel", "") or None
        voice_follow_users_str = credentials.get("voice_follow_users", "")
        voice_follow_users = [u.strip() for u in voice_follow_users_str.split(",") if u.strip()] if voice_follow_users_str else []
        voice_allowed_channels_str = credentials.get("voice_allowed_channels", "")
        voice_allowed_channels = (
            [c.strip() for c in voice_allowed_channels_str.split(",") if c.strip()] if voice_allowed_channels_str else []
        )

        config = DiscordChannelConfig(
            bot_token=credentials.get("bot_token", ""),
            enable_gateway=enable_gateway,
            allowed_users=allowed_users,
            allowed_guilds=allowed_guilds,
            auto_thread=auto_thread,
            no_thread_channels=no_thread_channels,
            voice_enabled=voice_enabled,
            voice_barge_in_enabled=voice_barge_in_enabled,
            voice_wake_words=voice_wake_words,
            voice_timeout=voice_timeout,
            voice_auto_join_channel=voice_auto_join,
            voice_text_channel=voice_text_channel,
            voice_follow_users=voice_follow_users,
            voice_allowed_channels=voice_allowed_channels,
        )
        instance = cls(config)
        instance._apply_bot_policy(credentials.get("bot_policy", "deny"))
        return instance

    capabilities = ChannelCapabilities(
        buttons=True,
        quick_replies=False,
        select_menus=True,
        threads=True,
        edit=True,
        delete=True,
        reactions=True,
        media=True,
        file_upload=True,
        typing_indicator=True,
        typing_keepalive_interval=8.0,
        max_text_length=MAX_TEXT_LENGTH,
    )

    def __init__(self, config: DiscordChannelConfig):
        super().__init__()
        self.config: DiscordChannelConfig = config
        self._client: discord.Client | None = None
        self._gateway_task: asyncio.Task[None] | None = None
        self._voice_manager: VoiceManager | None = None
        self._command_tree: discord.app_commands.CommandTree | None = None

    def _apply_bot_policy(self, raw: str) -> None:
        """Parse bot_policy credential and update allow_policy if needed."""
        policy = self._BOT_POLICY_MAP.get(raw.strip().lower(), ChatPolicy.DENY)
        if policy != ChatPolicy.DENY:
            self.allow_policy = AllowPolicy(
                allowlist=self.allow_policy.allowlist,
                denylist=self.allow_policy.denylist,
                dm_policy=self.allow_policy.dm_policy,
                group_policy=self.allow_policy.group_policy,
                bot_policy=policy,
                chat_overrides=self.allow_policy.chat_overrides,
            )

    # ── Lifecycle ──

    async def start(self) -> None:
        if self._status == ChannelStatus.RUNNING:
            return
        logger.info("Starting Discord channel (gateway=%s)", self.config.enable_gateway)
        if self.config.enable_gateway:
            await self._start_gateway()
        else:
            self._status = ChannelStatus.RUNNING

    async def _start_gateway(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        if self.config.voice_enabled:
            intents.voice_states = True

        self._client = discord.Client(intents=intents)
        channel_self = self

        if self.config.voice_enabled:
            self._command_tree = discord.app_commands.CommandTree(self._client)
            self._register_voice_commands()

        @self._client.event
        async def on_ready() -> None:
            logger.info("Discord gateway connected as %s", self._client.user)  # type: ignore[union-attr]
            if channel_self.config.voice_enabled:
                channel_self._init_voice_manager()
            if channel_self._command_tree:
                await channel_self._command_tree.sync()
                logger.info("Discord slash commands synced")
            self._status = ChannelStatus.RUNNING
            if channel_self.config.voice_enabled and channel_self.config.voice_auto_join_channel:
                await channel_self._auto_join()
            if channel_self.config.voice_enabled and channel_self._voice_manager and channel_self._voice_manager.follow_enabled:
                await channel_self._voice_manager.start_reconciliation()

        @self._client.event
        async def on_message(message: discord.Message) -> None:
            await channel_self._on_message(message)

        @self._client.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            await channel_self._on_interaction(interaction)

        @self._client.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent) -> None:
            await channel_self._on_reaction_add(payload)

        @self._client.event
        async def on_voice_state_update(
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState,
        ) -> None:
            if channel_self._voice_manager:
                await channel_self._voice_manager.on_voice_state_update(member, before, after)

        loop = asyncio.get_running_loop()
        self._gateway_task = loop.create_task(self._client.start(self.config.bot_token))

    async def stop(self) -> None:
        if self._status == ChannelStatus.STOPPED:
            return
        logger.info("Stopping Discord channel")
        if self._voice_manager:
            await self._voice_manager.leave_all()
            self._voice_manager = None
        if self._client and not self._client.is_closed():
            await self._client.close()
        if self._gateway_task:
            self._gateway_task.cancel()
            try:
                if isinstance(self._gateway_task, asyncio.Task):
                    await self._gateway_task
            except asyncio.CancelledError:
                pass
        self._status = ChannelStatus.STOPPED

    async def health_check(self) -> bool:
        """Verify Discord connectivity via REST API probe.

        discord.py reconnects internally on clean WS drops, but when the
        underlying socket is wedged behind a dead proxy/NAT the WS never
        sees a RST and the adapter sits in a zombie state.  An out-of-band
        ``fetch_user`` call exercises the REST path and lets the Gateway's
        ``_health_loop`` detect the wedge and trigger a restart.
        """
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        if not self.config.enable_gateway:
            return True
        if self._gateway_task and self._gateway_task.done():
            self.health.record_failure("Gateway task terminated")
            return False
        if not self._client or self._client.is_closed():
            self.health.record_failure("Client closed")
            return False
        user = self._client.user
        if not user:
            return True
        try:
            await asyncio.wait_for(
                self._client.fetch_user(user.id),
                timeout=_HEALTH_PROBE_TIMEOUT,
            )
            self.health.record_success()
            return True
        except Exception as exc:
            self.health.record_failure(str(exc)[:200])
            return False
