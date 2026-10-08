"""DingTalk inbound: webhook callbacks, Stream API WebSocket session and media download-code resolution.

[INPUT]
- channels.providers.dingtalk.api::DingTalkApiClient (POS: OpenAPI client)
- channels.providers.dingtalk.helpers::parse_callback, verify_signature (POS: pure callback helpers)
- channels.types::InboundMessage, MediaAttachment (POS: channel message value types)

[OUTPUT]
- DingTalkInboundMixin: handle_webhook / verify_webhook_signature and the Stream API session used by DingTalkChannel

[POS]
Inbound half of DingTalkChannel. The host owns credentials, token lifecycle and outbound delivery; the mixin only
converts DingTalk callbacks into InboundMessage and keeps the group-conversation routing cache.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging

from app.channels.core.exceptions import ChannelSendError
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
)

from .api import DingTalkApiClient
from .helpers import (
    ParsedCallback,
    parse_callback,
    verify_signature,
)

logger = logging.getLogger(__name__)

_GROUP_CACHE_MAX = 500


class DingTalkInboundMixin:
    """DingTalk inbound handling for ``DingTalkChannel``.

    Requires the host class to provide the attributes below plus ``_emit_inbound`` / ``_build_inbound``
    from ``BaseChannel``.
    """

    _app_secret: str
    _robot_code: str
    _api: DingTalkApiClient
    _group_conversations: set[str]
    _chat_sender_map: dict[str, str]

    async def handle_webhook(self, body: dict[str, object]) -> None:
        """Process a DingTalk robot callback (HTTP webhook mode)."""
        msg = self._inbound_from_event(body)
        if msg:
            msg = await self._resolve_media_codes(msg)
            await self._emit_inbound(msg)

    def verify_webhook_signature(self, timestamp: str, sign: str) -> bool:
        """Verify DingTalk webhook HMAC-SHA256 signature."""
        return verify_signature(self._app_secret, timestamp, sign)

    def _inbound_from_event(self, body: dict[str, object]) -> InboundMessage | None:
        """Parse a DingTalk event body and build an InboundMessage."""
        parsed: ParsedCallback | None = parse_callback(body, self._robot_code)
        if not parsed:
            return None
        is_group = parsed["is_group"]
        chat_id = parsed["chat_id"]
        if is_group:
            self._register_group(chat_id)
        else:
            self._chat_sender_map[chat_id] = parsed["sender_id"]

        sent_at = __import__("time").time()
        create_at = body.get("createAt")
        if create_at is not None:
            try:
                sent_at = float(create_at) / 1000.0
            except (ValueError, TypeError):
                pass

        return self._build_inbound(
            sender_id=parsed["sender_id"],
            content=parsed["content"],
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=chat_id,
            is_group=is_group,
            mentioned=parsed["mentioned"],
            media=parsed["media"],
            metadata=parsed["metadata"],
            message_id=parsed["message_id"],
        )

    def _register_group(self, conversation_id: str) -> None:
        """Cache a conversation ID as a group for outbound routing."""
        if len(self._group_conversations) >= _GROUP_CACHE_MAX:
            self._group_conversations.pop()
        self._group_conversations.add(conversation_id)

    async def _resolve_media_codes(self, msg: InboundMessage) -> InboundMessage:
        """Resolve DingTalk downloadCode values to actual download URLs.

        DingTalk sends temporary codes (not URLs) for media attachments.
        This resolves them via the Robot Message File Download API so
        downstream consumers (e.g. Vision LLM) can access the content.
        """
        if not msg.media:
            return msg

        codes_to_resolve = [
            (i, att) for i, att in enumerate(msg.media) if att.url and not att.url.startswith(("http://", "https://"))
        ]
        if not codes_to_resolve:
            return msg

        urls = await asyncio.gather(
            *(self._api.resolve_download_code(str(att.url)) for _, att in codes_to_resolve),
            return_exceptions=True,
        )

        resolved = list(msg.media)
        for (idx, att), url_result in zip(codes_to_resolve, urls, strict=True):
            if isinstance(url_result, str) and url_result:
                resolved[idx] = MediaAttachment(
                    media_type=att.media_type,
                    url=url_result,
                    path=att.path,
                    filename=att.filename,
                    mime_type=att.mime_type,
                )
            elif isinstance(url_result, BaseException):
                logger.warning("DingTalk: download code resolution error: %s", url_result)
            else:
                logger.warning("DingTalk: failed to resolve download code, keeping original")

        return dataclasses.replace(msg, media=tuple(resolved))

    async def _stream_once(self) -> None:
        """Single DingTalk Stream session. reconnect_loop handles retry on failure."""
        await self._api.ensure_token()
        endpoint, ticket = await self._api.open_stream_connection()

        if not endpoint:
            raise ChannelSendError("DingTalk stream: no endpoint returned", channel="dingtalk")

        import websockets as ws_lib

        async with ws_lib.connect(f"{endpoint}?ticket={ticket}") as ws:
            async for raw in ws:
                payload = json.loads(raw)
                headers = payload.get("headers", {})

                if headers.get("topic") == "/v1.0/im/bot/messages/get":
                    event_body = json.loads(payload.get("data", "{}"))
                    msg = self._inbound_from_event(event_body)
                    if msg:
                        msg = await self._resolve_media_codes(msg)
                        await self._emit_inbound(msg)

                msg_id_ack = headers.get("messageId")
                if msg_id_ack:
                    await ws.send(
                        json.dumps(
                            {
                                "code": 200,
                                "headers": {"contentType": "application/json", "messageId": msg_id_ack},
                                "message": "OK",
                                "data": "",
                            }
                        )
                    )
