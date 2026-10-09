"""Discord outbound: REST sending, forum threads and message maintenance.

[INPUT]
- app.channels.core.exceptions::ChannelSendError (POS: classified send failures; carries partial-delivery details)
- app.channels.providers.discord.helpers::build_discord_media, derive_thread_name, is_forum_channel, reply_reference (POS: attachments, forum detection and native reply targets)
- app.channels.rendering.renderer::render (POS: style-aware text chunking)

[OUTPUT]
- DiscordOutboundMixin: channel resolution, send / placeholder / edit / delete / react / typing used by DiscordChannel

[POS]
Outbound half of DiscordChannel. The host owns the gateway client; the mixin only talks to the Discord REST API through it.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Sequence

import discord

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.discord.helpers import build_discord_media, derive_thread_name, is_forum_channel, reply_reference
from app.channels.rendering.renderer import render
from app.channels.types import OutboundMessage
from app.channels.types.messages import RenderStyle

logger = logging.getLogger(__name__)


class DiscordOutboundMixin(BaseChannel):
    """Discord REST sending for ``DiscordChannel``.

    Requires the host class to provide the attributes below.
    """

    render_style: RenderStyle
    _client: discord.Client | None

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

    async def _create_forum_thread(
        self,
        forum: discord.ForumChannel,
        content: str,
        *,
        files: Sequence[discord.File] = (),
    ) -> str:
        """Create a new thread in a Forum channel and return the starter message ID.

        Handles the ``require_tag`` scenario: when a Forum is configured to
        require at least one tag, the first available tag is applied
        automatically so the API call does not fail. ``discord.DiscordException`` propagates.
        """
        applied_tags = forum.available_tags[:1] if forum.flags.require_tag else []
        thread = await forum.create_thread(
            name=derive_thread_name(content),
            content=content,
            files=list(files) or discord.utils.MISSING,
            applied_tags=applied_tags or discord.utils.MISSING,
        )

        starter_msg = getattr(thread, "message", None)
        thread_obj = thread if hasattr(thread, "send") else getattr(thread, "thread", None)
        thread_id = str(getattr(thread_obj, "id", getattr(thread, "id", "")))
        return str(getattr(starter_msg, "id", thread_id)) if starter_msg else thread_id

    async def send(self, message: OutboundMessage) -> str | None:
        channel = await self._resolve_channel(message.recipient_id)
        if not channel:
            raise ChannelSendError(f"Discord channel {message.recipient_id} is not reachable", channel=self.name)
        media = build_discord_media(message.media)
        # URL-only attachments travel as links in the text: Discord unfurls them and the splitter chunks them with it.
        outbound = dataclasses.replace(message, content="\n".join(filter(None, (message.content, *media.links))))
        try:
            if is_forum_channel(channel):
                sent_id: str | None = await self._create_forum_thread(channel, outbound.content, files=media.files)
            else:
                sent_id = await self._send_chunks(channel, outbound, media.files)
        except discord.HTTPException as exc:
            raise ChannelSendError(
                f"Discord send failed: {exc}",
                channel=self.name,
                status_code=exc.status,
                retriable=exc.status == 429 or exc.status >= 500,
            ) from exc
        except discord.DiscordException as exc:
            raise ChannelSendError(f"Discord send failed: {exc}", channel=self.name) from exc
        if media.failed:
            raise ChannelSendError.for_attachments(self.name, media.failed, delivered_any=sent_id is not None)
        return sent_id

    async def _send_chunks(
        self,
        channel: discord.abc.Messageable,
        message: OutboundMessage,
        files: list[discord.File],
    ) -> str | None:
        """Send the text in chunks with ``files`` on the first one (or files alone); return the last message id."""
        last_sent_id: str | None = None
        if message.content:
            for i, chunk in enumerate(render(message, self.render_style)):
                first = i == 0
                chunk_files = files if first and files else discord.utils.MISSING
                reference = reply_reference(channel, message.reply_to_id) if first and message.reply_to_id else None
                if reference is None:
                    sent = await channel.send(content=chunk, files=chunk_files)
                else:
                    sent = await channel.send(content=chunk, files=chunk_files, reference=reference)
                last_sent_id = str(sent.id)
        elif files:
            sent = await channel.send(files=files)
            last_sent_id = str(sent.id)
        return last_sent_id

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return None
        if is_forum_channel(channel):
            try:
                return await self._create_forum_thread(channel, text)
            except discord.DiscordException as exc:
                logger.error("Failed to create forum placeholder thread: %s", exc)
                return None
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
