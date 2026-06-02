"""Zalo channel — bidirectional messaging via Zalo OA API v3.

Inbound: webhook callback → handle_webhook → _emit_inbound
Outbound: text via message/cs, media via upload + attachment template

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- ZaloChannel: Zalo Official Account bidirectional messaging Channel

[POS]
Zalo Official Account channel. Supports bidirectional text/image/file messaging,
getoa health check, and collect_issues diagnostics.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
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
)

logger = logging.getLogger(__name__)

_API_V2 = "https://openapi.zalo.me/v2.0/oa/"
_API_V3 = "https://openapi.zalo.me/v3.0/oa/"
_SEND_TIMEOUT = 15.0
_UPLOAD_TIMEOUT = 30.0
_MAX_TEXT_LENGTH = 2000

_IMAGE_EVENTS = frozenset({"user_send_image", "user_send_gif", "user_send_sticker"})
_FILE_EVENTS = frozenset({"user_send_file", "user_send_audio", "user_send_video"})


class ZaloChannel(BaseChannel):
    """Zalo Official Account channel.

    Supports text/image/file bidirectional messaging via Zalo OA API v3.
    Media upload uses v2 API (upload/image, upload/file) to obtain attachment_id.
    """

    name = "zalo"
    credential_spec = credential_spec(
        "zaloCredentials",
        access_token=credential_field("accessToken", "ZALO_ACCESS_TOKEN"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(format="text", max_text_length=_MAX_TEXT_LENGTH)

    def __init__(self, access_token: str) -> None:
        super().__init__()
        self._token = access_token
        self._http = httpx.AsyncClient(
            headers={"access_token": access_token},
        )

    async def start(self) -> None:
        if not self._token:
            logger.info("Zalo token not configured; channel idle")
            return
        oa_id = await self._fetch_oa_id()
        if oa_id:
            self._bot_id = oa_id
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)
        logger.info("ZaloChannel: started (oa_id=%s)", self._bot_id or "unknown")

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._http.aclose()

    async def health_check(self) -> bool:
        try:
            resp = await self._http.get(f"{_API_V3}getoa", timeout=10.0)
            return resp.status_code == 200
        except Exception:
            return False

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._token:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="access_token not configured.",
                )
            )
            return issues
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Zalo OA connection failed. Check access_token validity.",
                )
            )
        return issues

    async def send(self, msg: OutboundMessage) -> str | None:
        last_msg_id: str | None = None

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
                last_msg_id = await self._send_text(msg.recipient_id, chunk)

        if msg.media:
            for att in msg.media:
                mid = await self._send_media(msg.recipient_id, att)
                if mid:
                    last_msg_id = mid

        return last_msg_id

    async def handle_webhook(self, body: dict[str, object]) -> None:
        """Process inbound webhook events from Zalo OA."""
        event_name = body.get("event_name", "")
        if not isinstance(event_name, str):
            return

        sender = body.get("sender")
        sender_id = ""
        if isinstance(sender, dict):
            raw_id = sender.get("id", "")
            sender_id = str(raw_id) if raw_id else ""

        msg_id = str(body.get("message_id", ""))

        if event_name == "user_send_text":
            await self._handle_text_event(sender_id, msg_id, body)
        elif event_name in _IMAGE_EVENTS:
            await self._handle_image_event(sender_id, msg_id, body)
        elif event_name in _FILE_EVENTS:
            await self._handle_file_event(sender_id, msg_id, body)

    # -- inbound handlers --

    async def _handle_text_event(self, sender_id: str, msg_id: str, body: dict[str, object]) -> None:
        message = body.get("message")
        text = ""
        if isinstance(message, dict):
            raw_text = message.get("text", "")
            text = str(raw_text) if raw_text else ""

        if not text.strip():
            return
        msg = self._build_inbound(
            sender_id=sender_id,
            content=text.strip(),
            chat_id=sender_id,
            is_group=False,
            mentioned=True,
            media=(),
            message_id=msg_id,
        )
        await self._emit_inbound(msg)

    async def _handle_image_event(self, sender_id: str, msg_id: str, body: dict[str, object]) -> None:
        message = body.get("message")
        url = ""
        if isinstance(message, dict):
            raw_url = message.get("url", "") or message.get("thumb", "")
            url = str(raw_url) if raw_url else ""

        if not url:
            return
        media = (MediaAttachment(url=url, media_type=MediaType.IMAGE),)
        msg = self._build_inbound(
            sender_id=sender_id,
            content="",
            chat_id=sender_id,
            is_group=False,
            mentioned=True,
            media=media,
            message_id=msg_id,
        )
        await self._emit_inbound(msg)

    async def _handle_file_event(self, sender_id: str, msg_id: str, body: dict[str, object]) -> None:
        message = body.get("message")
        url = ""
        if isinstance(message, dict):
            raw_url = message.get("url", "")
            url = str(raw_url) if raw_url else ""

        if not url:
            return
        media = (MediaAttachment(url=url, media_type=MediaType.DOCUMENT),)
        msg = self._build_inbound(
            sender_id=sender_id,
            content="",
            chat_id=sender_id,
            is_group=False,
            mentioned=True,
            media=media,
            message_id=msg_id,
        )
        await self._emit_inbound(msg)

    # -- outbound helpers --

    async def _send_text(self, user_id: str, text: str) -> str | None:
        payload: dict[str, object] = {
            "recipient": {"user_id": user_id},
            "message": {"text": text},
        }
        return await self._post_message(payload)

    async def _send_media(self, user_id: str, att: MediaAttachment) -> str | None:
        attachment_id = await self._upload_media(att)
        if not attachment_id:
            logger.debug("Zalo media upload failed for %s", att.url or att.path)
            return None

        is_image = att.media_type == MediaType.IMAGE
        media_type = "image" if is_image else "file"

        payload: dict[str, object] = {
            "recipient": {"user_id": user_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [
                            {
                                "media_type": media_type,
                                "attachment_id": attachment_id,
                            }
                        ],
                    },
                }
            },
        }
        return await self._post_message(payload)

    async def _upload_media(self, att: MediaAttachment) -> str | None:
        """Upload media to Zalo and return attachment_id."""
        is_image = att.media_type == MediaType.IMAGE
        endpoint = f"{_API_V2}upload/image" if is_image else f"{_API_V2}upload/file"

        if att.path:
            file_bytes = Path(att.path).read_bytes()
            filename = Path(att.path).name
        elif att.url:
            from app.channels.media import (
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(timeout_seconds=_UPLOAD_TIMEOUT)
            downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
            result = await downloader.download(att.url, config=config)
            if not result.success or not result.data:
                return None
            file_bytes = result.data
            filename = att.url.rsplit("/", 1)[-1] or "file"
        else:
            return None

        try:
            resp = await self._http.post(
                endpoint,
                files={"file": (filename, file_bytes)},
                timeout=_UPLOAD_TIMEOUT,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, dict) and data.get("error") == 0:
                raw_data = data.get("data")
                if isinstance(raw_data, dict):
                    aid = raw_data.get("attachment_id", "")
                    return str(aid) if aid else None
        except Exception:
            logger.debug("Zalo media upload failed")
        return None

    async def _post_message(self, payload: dict[str, object]) -> str | None:
        """Post a message to Zalo OA API and return msg_id if available."""
        try:
            resp = await self._http.post(
                f"{_API_V3}message/cs",
                json=payload,
                timeout=_SEND_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.debug("Zalo send failed: HTTP %d", resp.status_code)
                return None
            data = resp.json()
            if isinstance(data, dict) and data.get("error") == 0:
                raw_data = data.get("data")
                if isinstance(raw_data, dict):
                    mid = raw_data.get("message_id", "")
                    return str(mid) if mid else None
        except Exception:
            logger.debug("Zalo send exception")
        return None

    async def _fetch_oa_id(self) -> str:
        """Fetch OA ID via getoa API for _bot_id."""
        try:
            resp = await self._http.get(f"{_API_V3}getoa", timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and data.get("error") == 0:
                    raw_data = data.get("data")
                    if isinstance(raw_data, dict):
                        oa_id = raw_data.get("oa_id", "")
                        return str(oa_id) if oa_id else ""
        except Exception:
            logger.debug("Zalo: failed to fetch OA ID")
        return ""
