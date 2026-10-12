"""LINE inbound: webhook signature check, event routing, message / postback parsing and mention handling.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies _emit_inbound / _build_inbound / emit)
- channels.providers.line.helpers (POS: webhook payload types, reply-token wrapper and chat id resolution)
- channels.providers.line.user_resolver::LINEUserResolver (POS: sender display-name resolution)
- channels.types::MediaAttachment (POS: channel message value types)

[OUTPUT]
- LINEInboundMixin: verify_signature, handle_webhook and the message / postback / lifecycle handlers used by LINEChannel

[POS]
Inbound half of LINEChannel. The host owns the credentials, the reply / quote token caches and the user resolver; the mixin only parses webhook events.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import cast

from app.channels.core.base import BaseChannel
from app.channels.providers.line.helpers import (
    _DATA_API_BASE,
    _MEDIA_TYPE_MAP,
    _Event,
    _Message,
    _ReplyToken,
    _Source,
    resolve_chat_id,
)
from app.channels.providers.line.user_resolver import LineChatScope, LINEUserResolver
from app.channels.types import (
    MediaAttachment,
)

logger = logging.getLogger(__name__)


class LINEInboundMixin(BaseChannel):
    """LINE webhook event handling for ``LINEChannel``.

    Requires the host class to provide the attributes below.
    """

    _secret: str
    _bot_user_id: str
    _bot_display_name: str
    _reply_tokens: dict[str, _ReplyToken]
    _quote_tokens: dict[str, str]
    _user_resolver: LINEUserResolver

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not self._secret:
            return True
        digest = hmac.new(
            self._secret.encode(),
            body,
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, body: dict[str, object]) -> None:
        events = body.get("events")
        if not isinstance(events, list):
            return
        for raw in events:
            if not isinstance(raw, dict):
                continue
            event = cast(_Event, raw)
            await self._route_event(event)

    async def _route_event(self, event: _Event) -> None:
        etype = event.get("type", "")
        if etype == "message":
            await self._handle_message(event)
        elif etype == "postback":
            await self._handle_postback(event)
        elif etype in ("follow", "unfollow", "join", "leave"):
            self._handle_lifecycle(event)

    async def _handle_message(self, event: _Event) -> None:
        source = event.get("source", {})
        sender_id = source.get("userId", "")
        if not sender_id:
            return

        if self._bot_user_id and sender_id == self._bot_user_id:
            return

        chat_id = resolve_chat_id(source)
        is_group = source.get("type", "") in ("group", "room")

        reply_token = event.get("replyToken", "")
        if reply_token:
            self._reply_tokens[chat_id] = _ReplyToken(reply_token)

        message = event.get("message", {})
        msg_type = message.get("type", "")
        msg_id = message.get("id", "")

        quote_token = message.get("quoteToken", "")
        if quote_token:
            self._quote_tokens[chat_id] = quote_token

        content = ""
        media_list: list[MediaAttachment] = []

        if msg_type == "text":
            content = message.get("text", "")
        elif msg_type == "sticker":
            content = "[sticker]"
        elif msg_type == "location":
            content = "[location]"
        elif msg_type in _MEDIA_TYPE_MAP:
            mt = _MEDIA_TYPE_MAP[msg_type]
            download_url = f"{_DATA_API_BASE}/message/{msg_id}/content"
            media_list.append(
                MediaAttachment(
                    media_type=mt,
                    url=download_url,
                    filename=message.get("fileName"),
                )
            )

        if not content.strip() and not media_list:
            return

        mentioned = self._is_bot_mentioned(message) if is_group else False
        if is_group and mentioned:
            content = self._strip_bot_mention(content, message)

        metadata: dict[str, object] = {"replyToken": reply_token}

        scope = self._source_scope(source)
        await self._emit_inbound(
            self._build_inbound(
                sender_id=sender_id,
                content=content.strip(),
                chat_id=chat_id,
                is_group=is_group,
                mentioned=mentioned,
                media=tuple(media_list),
                metadata=metadata,
                message_id=msg_id,
                sender_name=await self._resolve_sender_name(sender_id, scope=scope, chat_id=chat_id),
            )
        )

    async def _handle_postback(self, event: _Event) -> None:
        source = event.get("source", {})
        sender_id = source.get("userId", "")
        if not sender_id:
            return

        postback = event.get("postback", {})
        data = postback.get("data", "")
        if not data:
            return

        chat_id = resolve_chat_id(source)
        is_group = source.get("type", "") in ("group", "room")

        reply_token = event.get("replyToken", "")
        if reply_token:
            self._reply_tokens[chat_id] = _ReplyToken(reply_token)

        metadata: dict[str, object] = {"replyToken": reply_token}

        scope = self._source_scope(source)
        await self._emit_inbound(
            self._build_inbound(
                sender_id=sender_id,
                content=data,
                chat_id=chat_id,
                is_group=is_group,
                mentioned=False,
                metadata=metadata,
                sender_name=await self._resolve_sender_name(sender_id, scope=scope, chat_id=chat_id),
            )
        )

    @staticmethod
    def _source_scope(source: _Source) -> LineChatScope:
        """Map a LINE event source type to a resolver scope."""
        src_type = source.get("type", "")
        if src_type == "group":
            return "group"
        if src_type == "room":
            return "room"
        return "user"

    async def _resolve_sender_name(
        self,
        sender_id: str | None,
        *,
        scope: LineChatScope = "user",
        chat_id: str = "",
    ) -> str | None:
        """Resolve a LINE sender's display name via profile API (fail-open).

        Selects the endpoint by chat scope: 1:1 users use Get Profile, while
        group/room members use their member profile API (works even when the
        member has not added the bot as a friend).

        Returns None when the ID is missing, resolution fails, or the user
        cannot be found — callers fall back to the opaque user ID.
        """
        if not sender_id:
            return None
        try:
            return await self._user_resolver.resolve_user(
                sender_id,
                scope=scope,
                chat_id=chat_id,
            )
        except Exception:
            logger.debug("Failed to resolve LINE sender name for %s", sender_id)
            return None

    def _handle_lifecycle(self, event: _Event) -> None:
        etype = event.get("type", "")
        source = event.get("source", {})
        src_type = source.get("type", "")
        target_id = source.get("groupId", "") or source.get("roomId", "") or source.get("userId", "")
        logger.info("LINE %s event: %s %s", etype, src_type, target_id)
        self.emit(f"line:{etype}", {"source_type": src_type, "id": target_id})

    def _is_bot_mentioned(self, message: _Message) -> bool:
        mention = message.get("mention")
        if not mention:
            return self._check_text_mention(message.get("text", ""))

        mentionees = mention.get("mentionees", [])
        for m in mentionees:
            if m.get("isSelf") is True:
                return True
            if m.get("type") == "all":
                return True
            if self._bot_user_id and m.get("userId") == self._bot_user_id:
                return True

        if self._bot_display_name:
            text = message.get("text", "")
            for m in mentionees:
                idx = m.get("index", -1)
                length = m.get("length", 0)
                if idx >= 0 and length > 0:
                    chars = list(text)
                    end = idx + length
                    if end <= len(chars):
                        mention_text = "".join(chars[idx:end])
                        if self._bot_display_name in mention_text:
                            return True

        return self._check_text_mention(message.get("text", ""))

    def _check_text_mention(self, text: str) -> bool:
        if self._bot_display_name and f"@{self._bot_display_name}" in text:
            return True
        return False

    def _strip_bot_mention(self, text: str, message: _Message) -> str:
        mention = message.get("mention")
        if mention:
            mentionees = mention.get("mentionees", [])
            chars = list(text)
            for m in reversed(mentionees):
                should_strip = False
                if m.get("isSelf") is True or (self._bot_user_id and m.get("userId") == self._bot_user_id):
                    should_strip = True
                elif self._bot_display_name:
                    idx = m.get("index", -1)
                    length = m.get("length", 0)
                    if idx >= 0 and length > 0:
                        end = idx + length
                        if end <= len(chars):
                            mt = "".join(chars[idx:end])
                            if self._bot_display_name in mt:
                                should_strip = True
                if should_strip:
                    idx = m.get("index", -1)
                    length = m.get("length", 0)
                    if idx >= 0 and length > 0:
                        end = idx + length
                        if end <= len(chars):
                            chars[idx:end] = []
            return "".join(chars).strip()

        if self._bot_display_name:
            return text.replace(f"@{self._bot_display_name}", "").strip()
        return text
