"""DingTalk channel — bidirectional messaging via Stream API + OpenAPI.

Inbound: Stream API (WebSocket, zero public exposure) or HTTP webhook callback
Outbound: OpenAPI (Markdown/text/image/file) with DM/group routing
  - Three-level media fallback: URL direct → upload+send → file send → text fallback
  - AI Card streaming: create → stream update → finalize (打字机效果)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base)
- channels.reliability.reconnect::reconnect_loop (POS: auto-reconnect)

[OUTPUT]
- DingTalkChannel: DingTalk Robot bidirectional Channel

[POS]
DingTalk robot channel. Stream API WebSocket for inbound, OpenAPI for outbound.
Supports DM/group routing, media upload with fallback, AI Card streaming,
and structured diagnostics.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import re
import uuid
from pathlib import Path

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
    extract_cron_context,
)

from .api import DingTalkApiClient
from .helpers import (
    ParsedCallback,
    filename_from_url,
    guess_filename,
    guess_mime_type,
    guess_upload_type,
    parse_callback,
    verify_signature,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 20000
_GROUP_CACHE_MAX = 500
_NUMBERED_LIST_RE = re.compile(r"^\d+\.\s")


class DingTalkChannel(BaseChannel):
    """DingTalk Robot channel using Stream API (WebSocket) + OpenAPI.

    Inbound: Stream API WebSocket (zero public exposure) or HTTP webhook
    Outbound: OpenAPI (Markdown, text, image, file) with DM/group routing
    """

    name = "dingtalk"
    credential_spec = credential_spec(
        "dingtalkCredentials",
        app_key=credential_field("clientId", "DINGTALK_APP_KEY"),
        app_secret=credential_field("clientSecret", "DINGTALK_APP_SECRET"),
        robot_code=credential_field("robotCode", "DINGTALK_ROBOT_CODE"),
        card_template_id=credential_field(
            "cardTemplateId",
            "DINGTALK_CARD_TEMPLATE_ID",
            default="",
            required=False,
            is_sensitive=False,
        ),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=False,
        edit=True,
        reactions=True,
        typing_indicator=False,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        robot_code: str = "",
        card_template_id: str = "",
    ) -> None:
        super().__init__()
        self._app_key = app_key
        self._app_secret = app_secret
        self._robot_code = robot_code or app_key
        self._card_template_id = card_template_id
        self._api = DingTalkApiClient(app_key, app_secret, robot_code=self._robot_code)
        self._stream_task: asyncio.Task[None] | None = None
        self._group_conversations: set[str] = set()
        self._chat_sender_map: dict[str, str] = {}
        self._streaming_cards: dict[str, str] = {}
        self._reaction_cache: dict[str, str] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._app_key or not self._app_secret:
            logger.info("DingTalk credentials not configured; channel idle")
            return
        try:
            await self._api.refresh_token()
        except Exception as exc:
            logger.warning("DingTalkChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            await self._api.close()
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        self._stream_task = asyncio.create_task(
            reconnect_loop(
                self._stream_once,
                lambda: self._status,
                channel_name="DingTalkChannel",
            )
        )
        logger.info("DingTalkChannel: started")

    async def stop(self) -> None:
        for track_id in list(self._streaming_cards.values()):
            try:
                await self._api.streaming_update(track_id, "content", "", is_finalize=True)
            except Exception:
                logger.debug("Failed to finalize streaming card %s on stop", track_id)
        self._streaming_cards.clear()
        self._chat_sender_map.clear()
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        self._group_conversations.clear()
        await self._api.close()
        logger.info("DingTalkChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            await self._api.ensure_token()
            ok = bool(self._api.access_token)
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure()
            return ok
        except Exception:
            self.health.record_failure()
            return False

    # ── Inbound ───────────────────────────────────────────────────────

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

    # ── Media Code Resolution ────────────────────────────────────────

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

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        await self._api.ensure_token()
        recipient = msg.recipient_id
        if not recipient:
            logger.warning("DingTalkChannel: no recipient_id, skipping")
            return None

        is_group = recipient in self._group_conversations

        if msg.content:
            cron = extract_cron_context(msg)
            title = cron.job_name if cron else "Reply"
            for chunk in render(msg, self.render_style):
                await self._send_text(recipient, title, chunk, is_group=is_group, metadata=msg.metadata)

        for attachment in msg.media:
            ok = await self._send_attachment(recipient, attachment, is_group=is_group)
            if not ok:
                fname = guess_filename(attachment)
                await self._send_text(recipient, "Error", f"[Attachment send failed: {fname}]", is_group=is_group)

        return None

    @staticmethod
    def _normalize_dingtalk_markdown(text: str) -> str:
        """Normalize markdown for DingTalk's renderer quirks.

        DingTalk's markdown parser requires:
        - Blank line before numbered list items (otherwise list not rendered)
        - Code fences at column 0 (indented fences not parsed)
        """
        lines = text.split("\n")
        out: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_numbered = bool(_NUMBERED_LIST_RE.match(stripped))
            if is_numbered and i > 0 and out:
                prev = out[-1]
                if prev.strip() and not _NUMBERED_LIST_RE.match(prev.strip()):
                    out.append("")
            if stripped.startswith("```") and line != line.lstrip():
                line = line.lstrip()
            out.append(line)
        return "\n".join(out)

    async def _send_text(
        self,
        recipient: str,
        title: str,
        text: str,
        *,
        is_group: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> None:
        """Send a Markdown message via the appropriate API (DM/group/webhook)."""
        text = self._normalize_dingtalk_markdown(text)
        webhook_url = metadata.get("webhookUrl") if metadata else None
        if webhook_url:
            await self._api.post_webhook(
                str(webhook_url),
                {"msgtype": "markdown", "markdown": {"title": title, "text": text}},
            )
            return

        if is_group:
            await self._api.send_group_markdown(recipient, title, text)
        else:
            await self._api.send_dm_markdown(recipient, title, text)

    async def _send_attachment(
        self,
        recipient: str,
        att: MediaAttachment,
        *,
        is_group: bool = False,
    ) -> bool:
        """Send a media attachment with three-level fallback.

        1. Image URL → direct send via sampleImageMsg (DM only)
        2. Download/read → upload → send as image or file
        3. Return False so caller can send a text fallback

        Group attachments degrade to Markdown link (DingTalk group API limitation).
        """
        is_image = att.media_type == MediaType.IMAGE

        if not is_group and att.url and is_image:
            if await self._api.send_image_dm(recipient, att.url):
                return True
            logger.warning("DingTalk image URL direct send failed, trying upload: %s", att.url[:200])

        if is_group:
            url = att.url or att.path or ""
            fname = guess_filename(att)
            await self._api.send_group_markdown(recipient, "Attachment", f"\U0001f4ce [{fname}]({url})")
            return True

        data, filename, mime = await self._read_media(att)
        if not data:
            return False

        upload_type = guess_upload_type(filename)
        media_id = await self._api.upload_media(data, upload_type, filename, mime)
        if not media_id:
            return False

        if is_image or upload_type == "image":
            if await self._api.send_image_dm(recipient, media_id):
                return True
            logger.warning("DingTalk image media_id send failed, falling back to file: %s", filename)

        return await self._api.send_file_dm(recipient, media_id, filename)

    async def _read_media(self, att: MediaAttachment) -> tuple[bytes | None, str, str]:
        """Read media bytes from URL or local path. Returns (data, filename, mime)."""
        if att.url:
            result = await self._api.download_url(att.url)
            if result:
                data, content_type = result
                filename = filename_from_url(att.url)
                mime = att.mime_type or content_type or "application/octet-stream"
                return data, filename, mime

        if att.path:
            path = Path(att.path)
            if not path.is_file():
                logger.warning("DingTalk attachment file not found: %s", att.path)
                return None, "", ""
            data = await asyncio.to_thread(path.read_bytes)
            mime = att.mime_type or guess_mime_type(path.name)
            return data, path.name, mime

        return None, "", ""

    # ── Reaction ───────────────────────────────────────────────────────

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add or remove a reaction on a DingTalk message.

        Uses DingTalk's Robot Emotion API. Requires both message_id (msgId)
        and chat_id (openConversationId) which are captured during inbound parsing.
        """
        if not message_id or not chat_id:
            return
        try:
            if emoji:
                await self._api.send_emotion(message_id, chat_id, emoji)
            else:
                prev = self._reaction_cache.pop(message_id, "")
                if prev:
                    await self._api.recall_emotion(message_id, chat_id, prev)
                return
            self._reaction_cache[message_id] = emoji
        except Exception:
            logger.debug("DingTalk react_to_message failed: msg=%s", message_id[:24])

    # ── AI Card streaming ──────────────────────────────────────────────

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        if not self._card_template_id:
            return None

        await self._finalize_active_cards()

        is_group = chat_id in self._group_conversations
        out_track_id = uuid.uuid4().hex
        if is_group:
            open_space_id = f"dtv1.card//IM_GROUP.{chat_id}"
        else:
            sender_id = self._chat_sender_map.get(chat_id, chat_id)
            open_space_id = f"dtv1.card//IM_ROBOT.{sender_id}"

        ok = await self._api.create_and_deliver_card(
            self._card_template_id,
            out_track_id,
            open_space_id,
            is_group=is_group,
            card_data={"content": text or ""},
        )
        if ok:
            self._streaming_cards[out_track_id] = out_track_id
            return out_track_id
        return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if message_id not in self._streaming_cards:
            return
        text = self._normalize_dingtalk_markdown(text)
        await self._api.streaming_update(message_id, "content", text, is_finalize=False)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        track_id = self._streaming_cards.pop(message_id, "")
        if not track_id:
            return
        content = self._normalize_dingtalk_markdown((msg.content or "")[:_MAX_TEXT_LENGTH])
        await self._api.streaming_update(track_id, "content", content, is_finalize=True)

    async def _finalize_active_cards(self) -> None:
        """Finalize all active streaming cards to prevent stale 'typing' state."""
        for track_id in list(self._streaming_cards.values()):
            try:
                await self._api.streaming_update(track_id, "content", "", is_finalize=True)
            except Exception:
                logger.debug("Failed to finalize stale card %s", track_id)
        self._streaming_cards.clear()

    # ── Stream API (WebSocket) ────────────────────────────────────────

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

    # ── Diagnostics ───────────────────────────────────────────────────

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._app_key or not self._app_secret:
            missing: list[str] = []
            if not self._app_key:
                missing.append("App Key")
            if not self._app_secret:
                missing.append("App Secret")
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"Missing credentials: {', '.join(missing)}",
                )
            )
        if not self._robot_code or self._robot_code == self._app_key:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="robot_code not set; using app_key as fallback",
                )
            )
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Channel in ERROR state; check credentials and network",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=f"Last error: {self.health.last_error}",
                )
            )
        return issues
