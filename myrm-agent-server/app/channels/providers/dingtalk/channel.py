"""DingTalk channel — bidirectional messaging via Stream API + OpenAPI.

Inbound: Stream API (WebSocket, zero public exposure) or HTTP webhook callback
Outbound: OpenAPI (Markdown/text/image/file) with DM/group routing
  - Three-level media fallback: URL direct → upload+send → file send; a failed attachment is reported to the bus
  - AI Card streaming: create → stream update → finalize (打字机效果)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base)
- channels.providers.dingtalk.inbound::DingTalkInboundMixin (POS: webhook / Stream API inbound)
- channels.providers.dingtalk.cards::DingTalkCardMixin (POS: AI Card streaming)
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
import logging
import re
from functools import partial
from pathlib import Path

from app.channels.core.attachment_delivery import deliver_attachments
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.reconnect import reconnect_loop
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
    extract_cron_context,
)

from .api import DingTalkApiClient
from .cards import DingTalkCardMixin
from .helpers import (
    MAX_TEXT_LENGTH,
    filename_from_url,
    guess_filename,
    guess_mime_type,
    guess_upload_type,
)
from .inbound import DingTalkInboundMixin

logger = logging.getLogger(__name__)

_NUMBERED_LIST_RE = re.compile(r"^\d+\.\s")


class DingTalkChannel(DingTalkCardMixin, DingTalkInboundMixin, BaseChannel):
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
        max_text_length=MAX_TEXT_LENGTH,
        message_ids=False,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=MAX_TEXT_LENGTH,
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

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        await self._api.ensure_token()
        recipient = msg.recipient_id
        if not recipient:
            raise ChannelSendError("DingTalk message has no recipient", channel=self.name, retriable=False)

        is_group = recipient in self._group_conversations

        if msg.content:
            cron = extract_cron_context(msg)
            title = cron.job_name if cron else "Reply"
            for chunk in render(msg, self.render_style):
                await self._send_text(recipient, title, chunk, is_group=is_group, metadata=msg.metadata)

        await deliver_attachments(
            self.name,
            msg.media,
            partial(self._send_attachment, recipient, is_group=is_group),
            text_delivered=bool(msg.content),
        )
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
        """Send a Markdown message via the appropriate API (DM/group/webhook); raise when DingTalk rejects it."""
        text = self._normalize_dingtalk_markdown(text)
        webhook_url = metadata.get("webhookUrl") if metadata else None
        if webhook_url:
            sent = await self._api.post_webhook(
                str(webhook_url),
                {"msgtype": "markdown", "markdown": {"title": title, "text": text}},
            )
        elif is_group:
            sent = await self._api.send_group_markdown(recipient, title, text)
        else:
            sent = await self._api.send_dm_markdown(recipient, title, text)
        if not sent:
            raise ChannelSendError("DingTalk rejected the message", channel=self.name)

    async def _send_attachment(
        self,
        recipient: str,
        att: MediaAttachment,
        *,
        is_group: bool = False,
    ) -> None:
        """Send one attachment with a two-level fallback; raise when DingTalk does not accept it.

        1. Image URL → direct send via sampleImageMsg (DM only)
        2. Download/read → upload → send as image or file

        Group chats only accept a Markdown link (DingTalk group API limitation), so a local file
        without a URL cannot be delivered there.
        """
        is_image = att.media_type == MediaType.IMAGE

        if not is_group and att.url and is_image:
            if await self._api.send_image_dm(recipient, att.url):
                return
            logger.warning("DingTalk image URL direct send failed, trying upload: %s", att.url[:200])

        if is_group:
            if not att.url:
                raise ChannelSendError("DingTalk group chats cannot receive local files", channel=self.name, retriable=False)
            link = f"\U0001f4ce [{guess_filename(att)}]({att.url})"
            if not await self._api.send_group_markdown(recipient, "Attachment", link):
                raise ChannelSendError("DingTalk rejected the attachment link", channel=self.name)
            return

        data, filename, mime = await self._read_media(att)
        if not data:
            raise ChannelSendError("DingTalk attachment has no readable content", channel=self.name)

        upload_type = guess_upload_type(filename)
        media_id = await self._api.upload_media(data, upload_type, filename, mime)
        if not media_id:
            raise ChannelSendError("DingTalk media upload failed", channel=self.name)

        if is_image or upload_type == "image":
            if await self._api.send_image_dm(recipient, media_id):
                return
            logger.warning("DingTalk image media_id send failed, falling back to file: %s", filename)

        if not await self._api.send_file_dm(recipient, media_id, filename):
            raise ChannelSendError("DingTalk rejected the file message", channel=self.name)

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
