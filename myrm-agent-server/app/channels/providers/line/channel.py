"""LINE channel — bidirectional messaging via Messaging API.

Inbound: webhook → _route_event → _handle_message / _handle_postback.
Outbound: Reply (free) → Push (paid) fallback.

[INPUT]
- channels.core.base::BaseChannel, (POS: Provides FileOperationObserver.)
- channels.providers.line.inbound::LINEInboundMixin (POS: webhook signature check, event routing and message / postback parsing)

[OUTPUT]
- LINEChannel: LINE Messaging API bidirectional communication Channel (credentials, lifecycle, Reply / Push outbound); webhook inbound comes from the mixin

[POS]
LINE integration: webhook inbound, Reply/Push outbound, mention detection, quote-token context linking.
"""

from __future__ import annotations

import logging

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.line.api import LineClient
from app.channels.providers.line.helpers import (
    _MAX_MESSAGES_PER_REQUEST,
    _MAX_QUICK_REPLY_ITEMS,
    _MAX_TEXT_LENGTH,
    _QUICK_REPLY_LABEL_MAX,
    _ReplyToken,
)
from app.channels.providers.line.inbound import LINEInboundMixin
from app.channels.providers.line.user_resolver import LINEUserResolver
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


class LINEChannel(LINEInboundMixin, BaseChannel):
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
        self._user_resolver = LINEUserResolver(self._api)
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
            logger.info(
                "LINE bot info: userId=%s displayName=%s",
                self._bot_user_id,
                self._bot_display_name,
            )
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
        """Send text and media as Reply (free) or Push messages.

        LINE carries only public-URL images, videos and audio; any other attachment is reported after the
        rest went out, so the bus never replays what the recipient already has.
        """
        if not msg.recipient_id:
            raise ChannelSendError("LINE message has no recipient", channel=self.name, retriable=False)
        all_messages, unsupported = self._build_outbound_messages(msg)
        last_msg_id = await self._deliver(msg.recipient_id, all_messages) if all_messages else None
        if unsupported:
            raise ChannelSendError.for_attachments(self.name, unsupported, delivered_any=bool(all_messages), retriable=False)
        return last_msg_id

    async def _deliver(self, chat_id: str, all_messages: list[dict[str, object]]) -> str | None:
        reply_entry = self._reply_tokens.pop(chat_id, None)
        quote_token = self._quote_tokens.pop(chat_id, None)

        last_msg_id: str | None = None
        offset = 0
        batch_index = 0

        while offset < len(all_messages):
            batch = all_messages[offset : offset + _MAX_MESSAGES_PER_REQUEST]
            offset += len(batch)

            if batch_index == 0 and quote_token:
                first = batch[0]
                if first.get("type") == "text":
                    first["quoteToken"] = quote_token

            resp: httpx.Response | None = None
            pushed = False
            if batch_index == 0 and reply_entry and not reply_entry.expired:
                resp = await self._call_reply(reply_entry.token, batch)
                if resp is None:
                    logger.debug("LINE reply token failed, falling back to push")
            if resp is None:
                resp = await self._call_push(chat_id, batch)
                pushed = True

            data = self._parse_response(resp)
            if data:
                last_msg_id = self._extract_message_id_from(data) or last_msg_id
                if pushed:
                    self._store_quote_token(chat_id, data)
            batch_index += 1

        return last_msg_id

    def _build_outbound_messages(
        self,
        msg: OutboundMessage,
    ) -> tuple[list[dict[str, object]], list[str]]:
        """Build the LINE message objects and the names of attachments LINE cannot carry."""
        messages: list[dict[str, object]] = []
        unsupported: list[str] = []

        for ma in msg.media:
            media_msg = self._build_media_message(ma)
            if media_msg:
                messages.append(media_msg)
            else:
                unsupported.append(ma.display_name)

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
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

        return messages, unsupported

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
    ) -> httpx.Response | None:
        """Reply with the free token; ``None`` when LINE does not take it, so the caller falls back to push."""
        try:
            resp = await self._api.reply(reply_token, messages)
        except Exception as exc:
            logger.debug("LINE reply request failed: %s", exc)
            return None
        return None if resp.status_code >= 400 else resp

    async def _call_push(
        self,
        to: str,
        messages: list[dict[str, object]],
    ) -> httpx.Response:
        """Push messages; raises ``ChannelSendError`` when LINE does not take them."""
        try:
            resp = await self._api.push(to, messages)
        except Exception as exc:
            self.health.record_failure(str(exc))
            raise ChannelSendError(f"LINE request failed: {type(exc).__name__}", channel=self.name) from exc
        if resp.status_code >= 400:
            self.health.record_failure(f"HTTP {resp.status_code}")
            detail = (self._parse_response(resp) or {}).get("message")
            raise ChannelSendError.from_http_status(self.name, resp.status_code, str(detail or ""))
        return resp

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
