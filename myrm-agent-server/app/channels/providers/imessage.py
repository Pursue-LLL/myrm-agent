"""iMessage channel — via BlueBubbles HTTP API bridge.

Inbound: webhook callback → _parse_message → _emit_inbound
Outbound: REST API (text + multipart attachment) with Tapback reactions

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base)

[OUTPUT]
- IMessageChannel: iMessage bidirectional Channel (via BlueBubbles macOS bridge)

[POS]
iMessage channel via BlueBubbles API. Text/media send, Tapback reactions,
webhook authentication, structured diagnostics.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelConnectionError
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
)

logger = logging.getLogger(__name__)

_SEND_TIMEOUT = 15.0
_MEDIA_TIMEOUT = 30.0
_MAX_TEXT_LENGTH = 10000

_TAPBACK_MAP: dict[str, int] = {
    "\u2764\ufe0f": 2000,
    "\U0001f44d": 2001,
    "\U0001f44e": 2002,
    "\U0001f602": 2003,
    "\u2757": 2004,
    "\u203c\ufe0f": 2004,
    "\u2753": 2005,
    "\U0001f440": 2001,
}
_TAPBACK_CODE_TO_EMOJI: dict[int, str] = {
    2000: "\u2764\ufe0f",
    2001: "\U0001f44d",
    2002: "\U0001f44e",
    2003: "\U0001f602",
    2004: "\u2757",
    2005: "\u2753",
}


class IMessageChannel(BaseChannel):
    """iMessage channel via BlueBubbles API.

    Inbound: webhook callback (new-message events)
    Outbound: REST API (text + multipart attachment + Tapback reactions)
    """

    name = "imessage"
    credential_spec = credential_spec(
        "imessageCredentials",
        api_url=credential_field("apiUrl", "IMESSAGE_API_URL"),
        password=credential_field("password", "IMESSAGE_PASSWORD"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        reactions=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self, api_url: str, password: str) -> None:
        super().__init__()
        self._api_url = api_url.rstrip("/")
        self._password = password
        self._http = httpx.AsyncClient()

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._api_url:
            logger.info("iMessage API URL not configured; channel idle")
            return

        # Startup Validation & Adaptive Backoff
        max_retries = 5
        base_delay = 2.0

        for attempt in range(max_retries):
            try:
                resp = await self._http.get(
                    f"{self._api_url}/api/v1/server/info",
                    params={"password": self._password},
                    timeout=5.0,
                )
                if resp.status_code == 200:
                    self._status = ChannelStatus.RUNNING
                    self._set_connected(True)
                    logger.info("IMessageChannel: started successfully")
                    return
                else:
                    logger.warning(
                        "IMessageChannel: BlueBubbles bridge returned HTTP %d (attempt %d/%d)",
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                    )
            except Exception as exc:
                logger.warning(
                    "IMessageChannel: BlueBubbles bridge unreachable: %s (attempt %d/%d)", exc, attempt + 1, max_retries
                )

            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.info("IMessageChannel: Retrying connection in %.1fs...", delay)
                await asyncio.sleep(delay)

        # Fail-fast / Graceful Degradation
        self._status = ChannelStatus.DEGRADED
        self._set_connected(False)
        logger.error(
            " [iMessage startfailure] cannotconnectto BlueBubbles , checkitswhetheralreadyinbackgroundline (URL: %s)",
            self._api_url,
        )
        raise ChannelConnectionError(
            f"Failed to connect to BlueBubbles bridge at {self._api_url} after {max_retries} attempts",
            channel=self.name,
        )

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        await self._http.aclose()
        logger.info("IMessageChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            resp = await self._http.get(
                f"{self._api_url}/api/v1/server/info",
                params={"password": self._password},
                timeout=10.0,
            )
            ok = resp.status_code == 200
            if ok:
                self.health.record_success()
            else:
                self.health.record_failure(f"HTTP {resp.status_code}")
            return ok
        except Exception as exc:
            self.health.record_failure(str(exc))
            return False

    # ── Inbound ───────────────────────────────────────────────────────

    async def handle_webhook(self, body: dict[str, object]) -> None:
        """Process a BlueBubbles webhook event."""
        event_type = body.get("type", "")
        if event_type != "new-message":
            return
        data = body.get("data", {})
        if not isinstance(data, dict):
            return
        msg = self._parse_message(data)
        if msg:
            await self._emit_inbound(msg)

    def verify_webhook_password(self, body: dict[str, object]) -> bool:
        """Verify BlueBubbles webhook password (timing-safe comparison)."""
        if not self._password:
            return True
        incoming = str(body.get("password", ""))
        return hmac.compare_digest(incoming, self._password)

    def _parse_message(self, data: dict[str, object]) -> InboundMessage | None:
        if data.get("isFromMe", False):
            return None

        handle = data.get("handle", {})
        sender = str(handle.get("address", "")) if isinstance(handle, dict) else ""

        chats = data.get("chats")
        chat_guid = sender
        if isinstance(chats, list) and chats:
            first_chat = chats[0]
            if isinstance(first_chat, dict):
                chat_guid = str(first_chat.get("guid", sender))

        msg_guid = str(data.get("guid", ""))
        is_group = ";+;" in chat_guid

        reaction_msg = self._parse_tapback(data, sender, chat_guid, is_group)
        if reaction_msg:
            return reaction_msg

        content = str(data.get("text", "") or "")
        reply_to = str(data.get("threadOriginatorGuid", "") or "")

        media_list: list[MediaAttachment] = []
        attachments = data.get("attachments", [])
        if isinstance(attachments, list):
            for att in attachments:
                if not isinstance(att, dict):
                    continue
                mime = str(att.get("mimeType", ""))
                mt = _mime_to_media_type(mime)
                att_guid = str(att.get("guid", ""))
                url = f"{self._api_url}/api/v1/attachment/{att_guid}/download?password={self._password}" if att_guid else None
                transfer_name = att.get("transferName")
                fname = str(transfer_name) if transfer_name else None
                media_list.append(
                    MediaAttachment(
                        media_type=mt,
                        url=url,
                        filename=fname,
                        mime_type=mime,
                    )
                )

        if not content.strip() and not media_list:
            return None

        return self._build_inbound(
            sender_id=sender,
            content=content.strip(),
            chat_id=chat_guid,
            is_group=is_group,
            mentioned=False,
            media=tuple(media_list),
            message_id=msg_guid,
            reply_to_id=reply_to or None,
        )

    def _parse_tapback(
        self,
        data: dict[str, object],
        sender: str,
        chat_guid: str,
        is_group: bool,
    ) -> InboundMessage | None:
        """Detect and parse iMessage Tapback reactions from BlueBubbles webhook data."""
        assoc_type = data.get("associatedMessageType")
        if not isinstance(assoc_type, (int, float)):
            return None
        assoc_type_int = int(assoc_type)

        if not (2000 <= assoc_type_int < 3000):
            return None

        assoc_guid = str(data.get("associatedMessageGuid", "") or "")
        if assoc_guid.startswith("p:"):
            parts = assoc_guid.split("/", 1)
            assoc_guid = parts[1] if len(parts) > 1 else assoc_guid

        if not assoc_guid:
            return None

        emoji = _TAPBACK_CODE_TO_EMOJI.get(assoc_type_int, "")
        if not emoji:
            return None

        return self._build_inbound(
            sender_id=sender,
            content=emoji,
            chat_id=chat_guid,
            is_group=is_group,
            mentioned=True,
            message_id=assoc_guid,
            metadata={"reaction": True, "target_message_id": assoc_guid},
        )

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        chat_guid = msg.recipient_id or ""
        if not chat_guid:
            logger.warning("iMessage send: no recipient_id")
            return None

        last_guid: str | None = None

        if msg.content:
            for chunk in render(msg, self.render_style):
                guid = await self._send_text(chat_guid, chunk)
                if guid:
                    last_guid = guid

        for attachment in msg.media:
            guid = await self._send_attachment(chat_guid, attachment)
            if guid:
                last_guid = guid

        return last_guid

    async def _send_text(self, chat_guid: str, text: str) -> str | None:
        """Send a text message. Returns message guid on success."""
        try:
            resp = await self._http.post(
                f"{self._api_url}/api/v1/message/text",
                params={"password": self._password},
                json={
                    "chatGuid": chat_guid,
                    "tempGuid": f"temp-{uuid.uuid4()}",
                    "message": text,
                },
                timeout=_SEND_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.warning("iMessage text send failed: HTTP %d", resp.status_code)
                return None
            body = resp.json()
            return str(body.get("data", {}).get("guid", "")) if isinstance(body.get("data"), dict) else None
        except Exception as exc:
            logger.warning("iMessage text send error: %s", exc)
            return None

    async def _send_attachment(self, chat_guid: str, att: MediaAttachment) -> str | None:
        """Send a media attachment via multipart upload."""
        data, filename, mime = await self._read_media(att)
        if not data:
            logger.warning("iMessage attachment: no data for %s", att.filename or "unknown")
            return None

        try:
            resp = await self._http.post(
                f"{self._api_url}/api/v1/message/attachment",
                params={"password": self._password},
                data={
                    "chatGuid": chat_guid,
                    "tempGuid": f"temp-{uuid.uuid4()}",
                    "name": filename,
                },
                files={"attachment": (filename, data, mime)},
                timeout=_MEDIA_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.warning("iMessage attachment send failed: HTTP %d", resp.status_code)
                return None
            body = resp.json()
            return str(body.get("data", {}).get("guid", "")) if isinstance(body.get("data"), dict) else None
        except Exception as exc:
            logger.warning("iMessage attachment send error: %s", exc)
            return None

    async def _read_media(self, att: MediaAttachment) -> tuple[bytes | None, str, str]:
        """Read media bytes from URL or local path."""
        if att.url:
            from app.channels.media import (
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(timeout_seconds=_MEDIA_TIMEOUT)
            downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
            result = await downloader.download(att.url, config=config)
            if result.success and result.data:
                name = att.filename or _filename_from_url(att.url)
                ct = att.mime_type or result.content_type
                return result.data, name, ct

        if att.path:
            path = Path(att.path)
            if path.is_file():
                data = await asyncio.to_thread(path.read_bytes)
                mime = att.mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                return data, path.name, mime

        return None, "", ""

    # ── Reactions ─────────────────────────────────────────────────────

    async def react_to_message(
        self,
        chat_id: str,
        message_id: str,
        emoji: str,
    ) -> None:
        """Send a Tapback reaction via BlueBubbles Private API."""
        tapback = _TAPBACK_MAP.get(emoji)
        if tapback is None:
            tapback = 2001  # fallback: "like"
        if not emoji:
            tapback = tapback + 1000  # BlueBubbles: +1000 = remove reaction

        try:
            resp = await self._http.post(
                f"{self._api_url}/api/v1/message/react",
                params={"password": self._password},
                json={
                    "chatGuid": chat_id,
                    "selectedMessageGuid": message_id,
                    "reaction": tapback,
                },
                timeout=_SEND_TIMEOUT,
            )
            if resp.status_code >= 400:
                logger.warning("iMessage reaction failed: HTTP %d", resp.status_code)
        except Exception as exc:
            logger.warning("iMessage reaction error: %s", exc)

    # ── Diagnostics ───────────────────────────────────────────────────

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._api_url:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="BlueBubbles API URL not configured",
                )
            )
        if not self._password:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.WARNING,
                    message="BlueBubbles password not set; webhook authentication disabled",
                )
            )
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Channel in ERROR state; check BlueBubbles server connectivity",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message=self.health.last_error,
                )
            )
        return issues


# ── Module-level helpers ──────────────────────────────────────────────


def _mime_to_media_type(mime: str) -> MediaType:
    if mime.startswith("image/"):
        return MediaType.IMAGE
    if mime.startswith("audio/"):
        return MediaType.AUDIO
    if mime.startswith("video/"):
        return MediaType.VIDEO
    return MediaType.DOCUMENT


def _filename_from_url(url: str) -> str:
    name = Path(urlparse(url).path).name
    return name or "download.bin"
