"""Discord channel implementation.

Supports two modes via `config.enable_gateway`:
- True (Standalone): Starts a discord.py Client to listen for WebSocket events.
- False (SaaS): Only uses REST API, relies on external webhook for inbound.

Voice channel support is enabled via `config.voice_enabled`. When active,
the bot can join voice channels, listen via RTP, transcribe speech (STT),
and play back TTS audio.

[INPUT]
- app.channels.types::ChannelCapabilities, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- app.channels.types.messages::MediaAttachment, MediaType, ReasoningDisplay, RenderStyle, ToolSummaryDisplay (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)
- app.channels.core.base::BaseChannel (POS: Channel abstraction layer. All providers inherit this class; Gateway manages them uniformly. Supports outbound (send) and inbound (on_inbound callback) bidirectional communication. Providers may declare credential_spec and from_credentials for self-contained credential management.)

[OUTPUT]
- DiscordChannel: Discord channel provider.

[POS]
Discord channel implementation with Forum channel support.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
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
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
)
from app.channels.types.messages import (
    MediaAttachment,
    MediaType,
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

_IMAGE_CONTENT_TYPES = frozenset(("image/png", "image/jpeg", "image/gif", "image/webp"))
_VIDEO_CONTENT_TYPES = frozenset(("video/mp4", "video/webm", "video/quicktime"))
_AUDIO_CONTENT_TYPES = frozenset(("audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4"))


class DiscordChannel(BaseChannel):
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
        typing_indicator=True,
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

    # ── Channel resolution ──

    async def _resolve_channel(self, chat_id: str) -> discord.abc.Messageable | None:
        """Resolve a channel ID to a Messageable, using cache then API fallback."""
        if not self._client:
            return None
        channel = self._client.get_channel(int(chat_id))
        if channel and isinstance(channel, discord.abc.Messageable):
            return channel
        try:
            channel = await self._client.fetch_channel(int(chat_id))
            if isinstance(channel, discord.abc.Messageable):
                return channel
        except Exception as exc:
            logger.warning("Failed to resolve channel %s: %s", chat_id, exc)
        return None

    # ── Forum support ──

    @staticmethod
    def _is_forum_channel(channel: discord.abc.Messageable | None) -> bool:
        """Check whether *channel* is a Discord Forum channel (type 15).

        Uses a dual check (isinstance + raw type value) for compatibility
        across discord.py versions where ForumChannel may not exist.
        """
        if channel is None:
            return False
        forum_cls = getattr(discord, "ForumChannel", None)
        if forum_cls and isinstance(channel, forum_cls):
            return True
        channel_type = getattr(channel, "type", None)
        if channel_type is not None:
            type_value = getattr(channel_type, "value", channel_type)
            if type_value == 15:
                return True
        return False

    @staticmethod
    def _derive_thread_name(content: str) -> str:
        """Extract a thread title from message content (first non-empty line, max 100 chars)."""
        for line in content.split("\n"):
            cleaned = line.strip().lstrip("#").strip()
            if cleaned:
                return cleaned[:100]
        return "New Post"

    async def _create_forum_thread(
        self,
        forum: discord.abc.Messageable,
        content: str,
    ) -> str | None:
        """Create a new thread in a Forum channel and return the starter message ID.

        Handles the ``require_tag`` scenario: when a Forum is configured to
        require at least one tag, the first available tag is applied
        automatically so the API call does not fail.
        """
        thread_name = self._derive_thread_name(content)
        kwargs: dict[str, object] = {"name": thread_name, "content": content}

        requires_tag = getattr(forum, "requires_tag", False)
        if callable(requires_tag):
            requires_tag = requires_tag()
        if requires_tag:
            available = getattr(forum, "available_tags", None) or []
            if available:
                kwargs["applied_tags"] = [available[0]]

        try:
            thread = await forum.create_thread(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            logger.error(
                "Failed to create forum thread in %s: %s",
                getattr(forum, "id", "?"),
                exc,
            )
            return None

        starter_msg = getattr(thread, "message", None)
        thread_obj = thread if hasattr(thread, "send") else getattr(thread, "thread", None)
        thread_id = str(getattr(thread_obj, "id", getattr(thread, "id", "")))
        return str(getattr(starter_msg, "id", thread_id)) if starter_msg else thread_id

    # ── Outbound ──

    async def send(self, message: OutboundMessage) -> str | None:
        channel = await self._resolve_channel(message.recipient_id)
        if not channel:
            return None
        if self._is_forum_channel(channel):
            return await self._create_forum_thread(channel, message.content)
        try:
            sent = await channel.send(content=message.content)
            return str(sent.id)
        except Exception as exc:
            logger.error("Failed to send Discord message: %s", exc)
            return None

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return None
        if self._is_forum_channel(channel):
            return await self._create_forum_thread(channel, text)
        try:
            sent = await channel.send(content=text)
            return str(sent.id)
        except Exception as exc:
            logger.error("Failed to send placeholder: %s", exc)
            return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.edit(content=text)
        except Exception as exc:
            logger.error("Failed to edit message %s: %s", message_id, exc)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            target = await channel.fetch_message(int(message_id))
            embed = discord.Embed(description=msg.content)
            if msg.reasoning:
                embed.set_footer(text=msg.reasoning[:2048])
            await target.edit(embed=embed)
        except Exception as exc:
            logger.error("Failed to edit placeholder message %s: %s", message_id, exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
        except Exception as exc:
            logger.error("Failed to delete message %s: %s", message_id, exc)

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not emoji:
            return
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.add_reaction(emoji)
        except Exception as exc:
            logger.error("Failed to react to message %s: %s", message_id, exc)

    async def start_typing(self, chat_id: str) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            await channel.typing()
        except Exception as exc:
            logger.error("Failed to start typing in %s: %s", chat_id, exc)

    # ── Inbound ──

    async def _on_message(self, message: discord.Message) -> None:
        """Process incoming Discord message from Gateway."""
        media = self._extract_media(message)
        content = message.content
        if not content and media:
            content = media[0].caption or ""

        topic: str | None = getattr(message.channel, "topic", None)
        if not topic and isinstance(message.channel, discord.Thread):
            parent = getattr(message.channel, "parent", None)
            if parent is not None:
                topic = getattr(parent, "topic", None)

        effective_chat_id = str(message.channel.id)
        is_thread = isinstance(message.channel, discord.Thread)
        thread_id: str | None = str(message.channel.id) if is_thread else None

        if await self._should_auto_thread(message, is_thread):
            thread = await self._auto_create_thread(message, content)
            if thread:
                effective_chat_id = str(thread.id)
                thread_id = effective_chat_id
                is_thread = True

        inbound = InboundMessage(
            channel=self.name,
            sender_id=str(message.author.id),
            sender_name=message.author.display_name,
            sent_at=time.time(),
            sent_timezone="UTC",
            chat_id=effective_chat_id,
            user_id=str(message.author.id),
            is_bot=message.author.bot,
            content=content,
            message_id=str(message.id),
            thread_id=thread_id,
            media=media,
            metadata={
                "guild_id": str(message.guild.id) if message.guild else None,
                "channel_topic": topic,
            },
        )
        await self._emit_inbound(inbound)

    async def _should_auto_thread(self, message: discord.Message, is_thread: bool) -> bool:
        """Determine if this message should trigger auto-thread creation."""
        if not self.config.auto_thread:
            return False
        if message.author.bot:
            return False
        if is_thread or isinstance(message.channel, discord.DMChannel):
            return False
        if self._is_forum_channel(message.channel):
            return False
        if getattr(message, "type", None) == discord.MessageType.reply:
            return False
        channel_id = str(message.channel.id)
        if channel_id in self.config.no_thread_channels:
            return False
        return not (self._client and self._client.user not in message.mentions)

    async def _auto_create_thread(self, message: discord.Message, content: str) -> discord.Thread | None:
        """Create a thread from the user message for conversation isolation."""
        import re

        cleaned = re.sub(r"<@[!&]?\d+>", "", content)
        cleaned = re.sub(r"<#\d+>", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        thread_name = self._derive_thread_name(cleaned) if cleaned else "Conversation"
        try:
            return await message.create_thread(name=thread_name, auto_archive_duration=1440)
        except Exception:
            logger.debug(
                "Auto-thread creation failed for message %s, falling back to channel reply",
                message.id,
            )
            return None

    @staticmethod
    def _extract_media(message: discord.Message) -> tuple[MediaAttachment, ...]:
        """Extract MediaAttachments from Discord message attachments."""
        if not message.attachments:
            return ()

        attachments: list[MediaAttachment] = []
        for att in message.attachments:
            ct = (att.content_type or "").split(";")[0].strip().lower()
            if ct in _IMAGE_CONTENT_TYPES or (att.width and att.height):
                media_type = MediaType.IMAGE
            elif ct in _VIDEO_CONTENT_TYPES:
                media_type = MediaType.VIDEO
            elif ct in _AUDIO_CONTENT_TYPES:
                media_type = MediaType.AUDIO
            else:
                media_type = MediaType.DOCUMENT

            attachments.append(
                MediaAttachment(
                    media_type=media_type,
                    url=att.url,
                    filename=att.filename,
                    mime_type=ct or None,
                )
            )
        return tuple(attachments)

    async def _on_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Convert a Discord reaction event to InboundMessage for approval."""
        if self._client.user and payload.user_id == self._client.user.id:
            return

        emoji = str(payload.emoji)
        chat_id = str(payload.channel_id)
        target_msg_id = str(payload.message_id)

        inbound = self._build_inbound(
            sender_id=str(payload.user_id),
            content=emoji,
            chat_id=chat_id,
            is_group=payload.guild_id is not None,
            mentioned=True,
            message_id=target_msg_id,
            metadata={"reaction": True, "target_message_id": target_msg_id},
        )
        await self._emit_inbound(inbound)

    async def _on_interaction(self, interaction: discord.Interaction) -> None:
        """Process incoming Discord interaction (button click, select menu)."""
        if interaction.type != discord.InteractionType.component:
            return

        await interaction.response.defer()

        data = interaction.data or {}
        custom_id = data.get("custom_id", "")
        action = custom_id.replace("act:", "", 1) if custom_id.startswith("act:") else custom_id

        ch = interaction.channel
        topic: str | None = getattr(ch, "topic", None)
        if not topic and isinstance(ch, discord.Thread):
            parent = getattr(ch, "parent", None)
            if parent is not None:
                topic = getattr(parent, "topic", None)

        inbound = InboundMessage(
            channel=self.name,
            sender_id=str(interaction.user.id),
            sender_name=interaction.user.display_name,
            sent_at=time.time(),
            sent_timezone="UTC",
            chat_id=str(interaction.channel_id),
            user_id=str(interaction.user.id),
            content=f"/action {action}",
            message_id=str(interaction.id),
            metadata={
                "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
                "interaction_type": "component",
                "custom_id": custom_id,
                "channel_topic": topic,
            },
        )
        await self._emit_inbound(inbound)

    # ── Voice ──

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

    def on_inbound(self, callback: Callable[[InboundMessage], Awaitable[None]]) -> None:
        """Register inbound message callback."""
        self._on_inbound = callback

    async def fetch_history(self, chat_id: str, limit: int = 15) -> list[InboundMessage]:
        """Fetch recent historical messages from Discord channel."""
        try:
            channel = await self._resolve_channel(chat_id)
            if not channel:
                logger.warning("Discord: Channel %s not found for history fetch", chat_id)
                return []

            inbounds = []
            # Fetch history utilizing discord.py async iterator
            async for raw_msg in channel.history(limit=limit):
                if raw_msg.author.bot or str(raw_msg.author.id) == self._bot_id:
                    continue

                media = self._extract_media(raw_msg)
                content = raw_msg.content
                if not content and media:
                    content = media[0].caption or ""

                if not content and not media:
                    continue

                topic = getattr(channel, "topic", None)
                is_thread = isinstance(channel, discord.Thread)
                thread_id = str(channel.id) if is_thread else None

                inbound = InboundMessage(
                    channel=self.name,
                    sender_id=str(raw_msg.author.id),
                    sender_name=raw_msg.author.display_name,
                    sent_at=raw_msg.created_at.timestamp(),
                    sent_timezone="UTC",
                    chat_id=chat_id,
                    user_id=str(raw_msg.author.id),
                    is_bot=raw_msg.author.bot,
                    content=content,
                    message_id=str(raw_msg.id),
                    thread_id=thread_id,
                    media=media,
                    metadata={
                        "guild_id": str(raw_msg.guild.id) if raw_msg.guild else None,
                        "channel_topic": topic,
                    },
                )
                inbounds.append(inbound)

            return list(reversed(inbounds))
        except Exception as e:
            logger.warning("Failed to fetch Discord history for %s: %s", chat_id, e)
            return []
