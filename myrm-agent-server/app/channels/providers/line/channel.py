"""LINE channel — bidirectional messaging via Messaging API.

Inbound: webhook → _route_event → _handle_message / _handle_postback.
Outbound: Reply (free) → Push (paid) fallback.

[INPUT]
- channels.core.base::BaseChannel, (POS: Provides FileOperationObserver.)

[OUTPUT]
- LINEChannel: LINE Messaging API bidirectional communication Channel

[POS]
LINE integration: webhook inbound, Reply/Push outbound, mention detection, quote-token context linking.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import cast

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.providers.line.api import LineClient
from app.channels.providers.line.helpers import (
    _DATA_API_BASE,
    _MAX_MESSAGES_PER_REQUEST,
    _MAX_QUICK_REPLY_ITEMS,
    _MAX_TEXT_LENGTH,
    _MEDIA_TYPE_MAP,
    _QUICK_REPLY_LABEL_MAX,
    _Event,
    _Message,
    _Postback,
    _ReplyToken,
    _Source,
    resolve_chat_id,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

logger = logging.getLogger(__name__)


class LINEChannel(BaseChannel):
    """LINE Messaging API channel.

    Features: text/media/quick-reply, reply-token cost optimization,
    mention detection (isSelf + userId + displayName), typing indicator,
    structured diagnostics, quote-token context linking.
    """

    name = "line"
    credential_spec = credential_spec(
        "lineCredentials",
        channel_access_token=credential_field("channelAccessToken", "LINE_CHANNEL_ACCESS_TOKEN"),
        channel_secret=credential_field("channelSecret", "LINE_CHANNEL_SECRET"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        buttons=False,
        quick_replies=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=_MAX_TEXT_LENGTH,
        supports_code_fence=False,
        supports_links=False,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(
        self,
        channel_access_token: str,
        *,
        channel_secret: str = "",
    ) -> None:
        super().__init__()
        self._token = channel_access_token
        self._secret = channel_secret
        self._api = LineClient(channel_access_token)
        self._bot_user_id = ""
        self._bot_display_name = ""
        self._reply_tokens: dict[str, _ReplyToken] = {}
        self._quote_tokens: dict[str, str] = {}

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        if not self._token:
            logger.info("LINE token not configured; channel idle")
            return
        try:
            info = await self._api.get_bot_info()
            self._bot_user_id = info.get("userId", "")
            self._bot_display_name = info.get("displayName", "")
            if self._bot_user_id:
                self._bot_id = self._bot_user_id
            logger.info("LINE bot info: userId=%s displayName=%s", self._bot_user_id, self._bot_display_name)
        except Exception as exc:
            logger.warning("Failed to fetch LINE bot info: %s", exc)
        await super().start()

    async def stop(self) -> None:
        await self._api.close()
        await super().stop()

    # -- health & diagnostics ------------------------------------------------

    async def health_check(self) -> bool:
        try:
            ok, err = await self._api.health_check()
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure(err)
            return ok
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._token:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="LINE channel access token not configured",
                    fix="Set channel_access_token when creating LINEChannel",
                )
            )
        if not self._secret:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="LINE channel secret not configured; webhook signature verification disabled",
                    fix="Set channel_secret to enable webhook signature verification",
                )
            )
        if self._status == ChannelStatus.DEGRADED:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=f"Channel degraded: {self.health.last_error}",
                )
            )
        return issues

    # -- outbound ------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        if not msg.recipient_id:
            logger.warning("LINE send: empty recipient_id, skipping")
            return None
        try:
            return await self._send_impl(msg)
        except Exception as exc:
            self.health.record_failure(str(exc))
            logger.debug("LINE send failed: %s", exc)
            return None

    async def _send_impl(self, msg: OutboundMessage) -> str | None:
        messages = self._build_outbound_messages(msg)
        if not messages:
            return None

        chat_id = msg.recipient_id
        reply_entry = self._reply_tokens.pop(chat_id, None)
        quote_token = self._quote_tokens.pop(chat_id, None)

        if quote_token and messages:
            first = messages[0]
            if first.get("type") == "text":
                first["quoteToken"] = quote_token

        if reply_entry and not reply_entry.expired:
            result = await self._call_reply(reply_entry.token, messages)
            if result is not None:
                return result
            logger.debug("LINE reply token failed, falling back to push")

        return await self._call_push(chat_id, messages)

    def _build_outbound_messages(
        self,
        msg: OutboundMessage,
    ) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []

        for ma in msg.media:
            media_msg = self._build_media_message(ma)
            if media_msg:
                messages.append(media_msg)

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks[:_MAX_MESSAGES_PER_REQUEST]:
                messages.append({"type": "text", "text": chunk})

        if msg.quick_replies and messages:
            items = [
                {
                    "type": "action",
                    "action": {
                        "type": "message",
                        "label": qr.label[:_QUICK_REPLY_LABEL_MAX],
                        "text": qr.text,
                    },
                }
                for qr in msg.quick_replies[:_MAX_QUICK_REPLY_ITEMS]
            ]
            messages[-1]["quickReply"] = {"items": items}

        return messages[:_MAX_MESSAGES_PER_REQUEST]

    @staticmethod
    def _build_media_message(ma: MediaAttachment) -> dict[str, object] | None:
        url = ma.url
        if not url:
            return None
        type_map = {MediaType.IMAGE: "image", MediaType.VIDEO: "video"}
        line_type = type_map.get(ma.media_type)
        if line_type:
            return {
                "type": line_type,
                "originalContentUrl": url,
                "previewImageUrl": url,
            }
        if ma.media_type == MediaType.AUDIO:
            return {
                "type": "audio",
                "originalContentUrl": url,
                "duration": 60000,
            }
        return None

    async def _call_reply(
        self,
        reply_token: str,
        messages: list[dict[str, object]],
    ) -> str | None:
        resp = await self._api.reply(reply_token, messages)
        if resp.status_code >= 400:
            return None
        return self._extract_message_id(resp)

    async def _call_push(
        self,
        to: str,
        messages: list[dict[str, object]],
    ) -> str | None:
        resp = await self._api.push(to, messages)
        if resp.status_code >= 400:
            logger.debug("LINE push failed: HTTP %d", resp.status_code)
            return None
        data = self._parse_response(resp)
        msg_id = self._extract_message_id_from(data) if data else None
        if data:
            self._store_quote_token(to, data)
        return msg_id

    @staticmethod
    def _extract_message_id(resp: httpx.Response) -> str | None:
        data = LINEChannel._parse_response(resp)
        return LINEChannel._extract_message_id_from(data) if data else None

    @staticmethod
    def _parse_response(resp: httpx.Response) -> dict[str, object] | None:
        try:
            return resp.json()  # type: ignore[no-any-return]
        except Exception:
            return None

    @staticmethod
    def _extract_message_id_from(data: dict[str, object]) -> str | None:
        sent = data.get("sentMessages")
        if isinstance(sent, list) and sent:
            return str(sent[0].get("id", ""))
        return None

    def _store_quote_token(
        self,
        chat_id: str,
        data: dict[str, object],
    ) -> None:
        sent = data.get("sentMessages")
        if isinstance(sent, list) and sent:
            qt = sent[0].get("quoteToken")
            if isinstance(qt, str) and qt:
                self._quote_tokens[chat_id] = qt

    # -- typing indicator ----------------------------------------------------

    async def start_typing(self, chat_id: str) -> None:
        await self._api.start_loading(chat_id)

    # -- webhook inbound -----------------------------------------------------

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

    # -- message handling ----------------------------------------------------

    async def _handle_message(self, event: _Event) -> None:
        source = cast(_Source, event.get("source", {}))
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

        message = cast(_Message, event.get("message", {}))
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
            )
        )

    async def _handle_postback(self, event: _Event) -> None:
        source = cast(_Source, event.get("source", {}))
        sender_id = source.get("userId", "")
        if not sender_id:
            return

        postback = cast(_Postback, event.get("postback", {}))
        data = postback.get("data", "")
        if not data:
            return

        chat_id = resolve_chat_id(source)
        is_group = source.get("type", "") in ("group", "room")

        reply_token = event.get("replyToken", "")
        if reply_token:
            self._reply_tokens[chat_id] = _ReplyToken(reply_token)

        metadata: dict[str, object] = {"replyToken": reply_token}

        await self._emit_inbound(
            self._build_inbound(
                sender_id=sender_id,
                content=data,
                chat_id=chat_id,
                is_group=is_group,
                mentioned=False,
                metadata=metadata,
            )
        )

    def _handle_lifecycle(self, event: _Event) -> None:
        etype = event.get("type", "")
        source = cast(_Source, event.get("source", {}))
        src_type = source.get("type", "")
        target_id = source.get("groupId", "") or source.get("roomId", "") or source.get("userId", "")
        logger.info("LINE %s event: %s %s", etype, src_type, target_id)
        self.emit(f"line:{etype}", {"source_type": src_type, "id": target_id})

    # -- mention detection ---------------------------------------------------

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
