"""Discord inbound: gateway event parsing and history reads.

[INPUT]
- app.channels.core.base::BaseChannel (POS: channel abstraction; supplies _emit_inbound / _build_inbound)
- app.channels.providers.discord.helpers::derive_thread_name, is_forum_channel (POS: forum detection and thread titles)
- app.channels.types::InboundMessage, ReplyContext, MediaAttachment, MediaType (POS: channel message value types)

[OUTPUT]
- DiscordInboundMixin: message / reaction / interaction parsing, reply context, media extraction, auto-threading and history fetch used by DiscordChannel

[POS]
Inbound half of DiscordChannel. The host owns the gateway client and the policy; the mixin only turns Discord events into InboundMessage.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from app.channels.core.base import BaseChannel
from app.channels.providers.discord.config import (
    DiscordChannelConfig,
)
from app.channels.providers.discord.helpers import derive_thread_name, is_forum_channel
from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    InboundMessage,
    ReplyContext,
)
from app.channels.types.messages import (
    MediaAttachment,
    MediaType,
)

logger = logging.getLogger(__name__)

_IMAGE_CONTENT_TYPES = frozenset(("image/png", "image/jpeg", "image/gif", "image/webp"))
_VIDEO_CONTENT_TYPES = frozenset(("video/mp4", "video/webm", "video/quicktime"))
_AUDIO_CONTENT_TYPES = frozenset(("audio/mpeg", "audio/ogg", "audio/wav", "audio/mp4"))


class DiscordInboundMixin(BaseChannel):
    """Discord gateway event parsing for ``DiscordChannel``.

    Requires the host class to provide the attributes below plus ``_resolve_channel`` from the outbound half.
    """

    config: DiscordChannelConfig
    _client: discord.Client | None

    if TYPE_CHECKING:

        async def _resolve_channel(self, chat_id: str) -> discord.abc.Messageable | None: ...

    def _parse_reply_context(self, message: discord.Message) -> tuple[ReplyContext | None, str | None]:
        """Parse Discord message reference into ReplyContext.

        Uses ``message.reference.resolved`` (discord.py's actual API) to access
        the referenced message. ``resolved`` can be ``Message``,
        ``DeletedReferencedMessage``, or ``None``. Only a full ``Message``
        yields rich context; otherwise falls back to ID-only.
        """
        ref = getattr(message, "reference", None)
        if not ref or not getattr(ref, "message_id", None):
            return None, None

        reply_to_id = str(ref.message_id)
        resolved = getattr(ref, "resolved", None)
        if not isinstance(resolved, discord.Message):
            return ReplyContext(message_id=reply_to_id, content=""), reply_to_id

        content = resolved.content or ""
        if resolved.embeds:
            embed_texts = [e.description or e.title or "" for e in resolved.embeds]
            extra = "\n".join(t for t in embed_texts if t)
            if extra:
                content = f"{content}\n{extra}" if content else extra

        media_list = self._extract_media(resolved)

        author = resolved.author
        sender_id = str(author.id) if author else None
        sender_name = getattr(author, "display_name", None) if author else None
        created_at = getattr(resolved, "created_at", None)

        return (
            ReplyContext(
                message_id=str(resolved.id),
                content=content.strip(),
                media=media_list,
                sender_id=sender_id,
                sender_name=sender_name,
                timestamp=created_at.timestamp() if created_at else None,
            ),
            reply_to_id,
        )

    def _strip_bot_mention_text(self, text: str, bot_id: int | None = None) -> str:
        """Remove leading/inline @bot mention from group trigger text for Prompt Cache optimization."""
        if not text:
            return text
        import re

        if bot_id:
            cleaned = re.sub(rf"<@!?{bot_id}>\s*[,:\-]*\s*", "", text).strip()
        else:
            cleaned = re.sub(r"<@!?[0-9]+>\s*[,:\-]*\s*", "", text).strip()
        return cleaned or text

    def _resolve_mentioned(self, message: discord.Message, is_group: bool, reply_to_id: str | None) -> tuple[bool, bool]:
        """Determine if the bot was mentioned in the message.

        Returns (mentioned, explicit_mention).
        In group chats, also treats replying to the bot's own message as
        an implicit mention — same pattern as Telegram [inbound.py:356-358],
        human senders only: another bot replying to our message must not
        wake the agent (bot-to-bot loop; see routing/_ARCH.md).
        """
        if not is_group:
            return False, False
        bot_user = self._client.user if self._client else None
        explicit = bool(bot_user and bot_user in getattr(message, "mentions", []))
        if explicit:
            return True, True
        if reply_to_id and not getattr(message.author, "bot", False):
            ref = getattr(message, "reference", None)
            resolved = getattr(ref, "resolved", None) if ref else None
            if isinstance(resolved, discord.Message):
                ref_author = resolved.author
                if ref_author and bot_user and ref_author.id == bot_user.id:
                    return True, False
        return False, False

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

        is_group = message.guild is not None
        reply_to, reply_to_id = self._parse_reply_context(message)
        mentioned, explicit_mention = self._resolve_mentioned(message, is_group, reply_to_id)

        bot_id = self._client.user.id if self._client and self._client.user else None
        if content and is_group and (explicit_mention or mentioned):
            content = self._strip_bot_mention_text(content, bot_id)

        metadata: dict[str, object] = {
            "guild_id": str(message.guild.id) if message.guild else None,
            "channel_topic": topic,
        }
        if explicit_mention:
            metadata[METADATA_EXPLICIT_MENTION_KEY] = "1"

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
            is_group=is_group,
            mentioned=mentioned,
            reply_to=reply_to,
            reply_to_id=reply_to_id,
            metadata=metadata,
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
        if is_forum_channel(message.channel):
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
        thread_name = derive_thread_name(cleaned) if cleaned else "Conversation"
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
        bot_user = self._client.user if self._client else None
        if bot_user and payload.user_id == bot_user.id:
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

        data = interaction.data
        custom_id = str(data.get("custom_id", "")) if data else ""
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
            is_group=interaction.guild_id is not None,
            mentioned=True,
            metadata={
                "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
                "interaction_type": "component",
                "custom_id": custom_id,
                "channel_topic": topic,
            },
        )
        await self._emit_inbound(inbound)

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
                thread_id = str(channel.id) if isinstance(channel, discord.Thread) else None

                reply_to, reply_to_id = self._parse_reply_context(raw_msg)

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
                    is_group=raw_msg.guild is not None,
                    reply_to=reply_to,
                    reply_to_id=reply_to_id,
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
