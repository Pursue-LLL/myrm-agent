"""Mattermost inbound: WebSocket event parsing (posted / reaction_added) and inbound media.

[INPUT]
- app.channels.core.base::BaseChannel (POS: Channel base class with unified send/receive contract; supplies _emit_inbound)
- app.channels.types::InboundMessage, MediaAttachment, MediaType (POS: channel message value types)
- app.channels.providers.mattermost.api::MattermostClient (POS: REST + WebSocket client)

[OUTPUT]
- MattermostInboundMixin: _ws_connect and the posted / reaction_added parsers used by MattermostChannel

[POS]
Inbound half of MattermostChannel. The host owns the API client and the bot identity; the mixin only turns WebSocket events into InboundMessage.
"""

from __future__ import annotations

import json
import logging

from app.channels import BaseChannel, InboundMessage
from app.channels.types import (
    MediaAttachment,
    MediaType,
)

from .api import MattermostClient

logger = logging.getLogger(__name__)


class MattermostInboundMixin(BaseChannel):
    """Mattermost WebSocket event handling for ``MattermostChannel``.

    Requires the host class to provide the attributes below.
    """

    _api: MattermostClient
    _bot_name: str

    # Mattermost reactions arrive as platform shortcodes (``+1``, ``thumbsup``,
    # ``white_check_mark`` …). Translate each into the canonical Unicode
    # symbol that ``parse_approval_command`` recognises, so the routing layer
    # can stay agnostic of channel-specific naming.
    _REACTION_EMOJI_MAP: dict[str, str] = {
        "+1": "\U0001f44d",
        "thumbsup": "\U0001f44d",
        "white_check_mark": "\u2705",
        "heavy_check_mark": "\u2705",
        "heart": "\u2764",
        "muscle": "\U0001f4aa",
        "handshake": "\U0001f91d",
        "infinity": "\u267e",
        "star": "\u2b50",
        "-1": "\U0001f44e",
        "thumbsdown": "\U0001f44e",
        "x": "\u274c",
        "no_entry": "\U0001f6ab",
        "no_entry_sign": "\U0001f6ab",
    }

    async def _ws_connect(self) -> None:
        """Single WebSocket session — runs until connection drops."""
        async for event in self._api.stream_events():
            event_type = event.get("event", "")
            if event_type == "posted":
                await self._handle_posted(event)
            elif event_type == "reaction_added":
                await self._handle_reaction_added(event)

    async def _handle_reaction_added(self, event: dict[str, object]) -> None:
        """Convert a Mattermost ``reaction_added`` WebSocket event to InboundMessage.

        Mattermost emoji names map onto the unified Unicode model
        (``parse_approval_command``) via :pyattr:`_REACTION_EMOJI_MAP`. Reactions
        whose ``user_id`` matches the bot are filtered upstream by the inbound
        pipeline (``BaseChannel._emit_inbound``), but we also short-circuit here
        for clarity.
        """
        data = event.get("data")
        if not isinstance(data, dict):
            return

        reaction_raw = data.get("reaction", "")
        if not isinstance(reaction_raw, str):
            return
        try:
            reaction = json.loads(reaction_raw)
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(reaction, dict):
            return

        user_id = str(reaction.get("user_id", ""))
        if not user_id or user_id == self._bot_id:
            return

        emoji_name = str(reaction.get("emoji_name", "")).strip()
        emoji = self._REACTION_EMOJI_MAP.get(emoji_name)
        if not emoji:
            return

        channel_id = str(reaction.get("channel_id", ""))
        target_post_id = str(reaction.get("post_id", ""))
        if not channel_id or not target_post_id:
            return

        channel_type = str(data.get("channel_type", ""))
        is_group = channel_type not in ("D", "")

        inbound = InboundMessage(
            channel="mattermost",
            sender_id=user_id,
            content=emoji,
            chat_id=channel_id,
            is_group=is_group,
            mentioned=True,
            message_id=target_post_id,
            metadata={
                "platform": "mattermost",
                "channel_type": channel_type,
                "reaction": True,
                "target_message_id": target_post_id,
            },
        )
        await self._emit_inbound(inbound)

    async def _handle_posted(self, event: dict[str, object]) -> None:
        """Parse a 'posted' WebSocket event into InboundMessage."""
        data = event.get("data")
        if not isinstance(data, dict):
            return

        post_raw = data.get("post", "")
        if not isinstance(post_raw, str):
            return

        try:
            post = json.loads(post_raw)
        except (json.JSONDecodeError, TypeError):
            return

        if not isinstance(post, dict):
            return

        user_id = str(post.get("user_id", ""))
        if not user_id or user_id == self._bot_id:
            return

        message = str(post.get("message", "")).strip()
        if not message:
            return

        channel_id = str(post.get("channel_id", ""))
        post_id = str(post.get("id", ""))
        root_id = str(post.get("root_id", ""))

        channel_type = str(data.get("channel_type", ""))
        is_group = channel_type not in ("D", "")

        mentioned = self._check_mentioned(data, is_group)
        message = self._strip_bot_mention(message)

        sender_name = str(data.get("sender_name", ""))

        file_ids = post.get("file_ids")
        media = self._build_inbound_media(file_ids)

        sent_at = __import__("time").time()
        create_at = post.get("create_at")
        if create_at is not None:
            try:
                sent_at = float(create_at) / 1000.0
            except (ValueError, TypeError):
                pass

        inbound = InboundMessage(
            channel="mattermost",
            sender_id=user_id,
            content=message,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=channel_id,
            sender_name=sender_name or None,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media),
            thread_id=root_id or None,
            metadata={
                "platform": "mattermost",
                "channel_type": channel_type,
            },
            message_id=post_id or None,
        )
        await self._emit_inbound(inbound)

    def _check_mentioned(self, data: dict[str, object], is_group: bool) -> bool:
        """Check if the bot was @mentioned. DMs always count as mentioned."""
        if not is_group:
            return True
        mentions_raw = data.get("mentions", "")
        if not isinstance(mentions_raw, str) or not mentions_raw:
            return False
        try:
            mention_ids = json.loads(mentions_raw)
            if isinstance(mention_ids, list):
                return self._bot_id in mention_ids
        except (json.JSONDecodeError, TypeError):
            pass
        return False

    def _strip_bot_mention(self, text: str) -> str:
        """Remove @botname mention from message text."""
        if not self._bot_name:
            return text
        stripped = text.replace(f"@{self._bot_name}", "").strip()
        return stripped or text

    def _build_inbound_media(
        self,
        file_ids: object,
    ) -> list[MediaAttachment]:
        """Build MediaAttachment list from post file_ids."""
        if not isinstance(file_ids, list) or not file_ids:
            return []
        attachments: list[MediaAttachment] = []
        for fid in file_ids:
            if not isinstance(fid, str) or not fid:
                continue
            url = f"{self._api.api_url}/files/{fid}"
            attachments.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    url=url,
                    filename=fid,
                ),
            )
        return attachments
