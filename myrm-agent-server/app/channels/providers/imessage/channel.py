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
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

from .helpers import (
    MAX_TEXT_LENGTH,
    MEDIA_TIMEOUT,
    SEND_TIMEOUT,
    TAPBACK_MAP,
    filename_from_url,
    quote_guid,
)
from .parser import parse_message
from .webhook import register_webhook, unregister_webhook

logger = logging.getLogger(__name__)


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
        webhook_url=credential_field("webhookUrl", "IMESSAGE_WEBHOOK_URL", required=False),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        file_upload=True,
        reactions=True,
        typing_keepalive_interval=55.0,
        max_text_length=MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(self, api_url: str, password: str, webhook_url: str = "") -> None:
        super().__init__()
        self._api_url = api_url.rstrip("/")
        self._password = password
        self._webhook_url = webhook_url.strip() if webhook_url else ""
        self._http = httpx.AsyncClient()
        self._private_api_available = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._api_url:
            logger.info("iMessage API URL not configured; channel idle")
            return

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
                    self._detect_private_api(resp)
                    self._status = ChannelStatus.RUNNING
                    self._set_connected(True)
                    await self._register_webhook()
                    logger.info("IMessageChannel: started successfully (private_api=%s)", self._private_api_available)
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

        self._status = ChannelStatus.DEGRADED
        self._set_connected(False)
        logger.error(
            "IMessageChannel: cannot connect to BlueBubbles bridge at %s after %d attempts",
            self._api_url,
            max_retries,
        )
        raise ChannelConnectionError(
            f"Failed to connect to BlueBubbles bridge at {self._api_url} after {max_retries} attempts",
            channel=self.name,
        )

    async def stop(self) -> None:
        await self._unregister_webhook()
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

    def _detect_private_api(self, resp: httpx.Response) -> None:
        """Extract private_api availability from BlueBubbles server/info response."""
        try:
            body = resp.json()
            data = body.get("data", {})
            if isinstance(data, dict):
                self._private_api_available = bool(data.get("private_api"))
        except Exception:
            pass

    async def _mark_read(self, chat_guid: str) -> None:
        """Send a read receipt for the chat (requires Private API)."""
        if not self._private_api_available or not chat_guid:
            return
        try:
            await self._http.post(
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_guid)}/read",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception:
            pass

    # ── Webhook Auto-Registration ────────────────────────────────────

    async def _register_webhook(self) -> None:
        await register_webhook(self._http, self._api_url, self._password, self._webhook_url)

    async def _unregister_webhook(self) -> None:
        await unregister_webhook(self._http, self._api_url, self._password, self._webhook_url)

    # ── Typing Indicator ──────────────────────────────────────────────

    async def start_typing(self, chat_id: str) -> None:
        if not self._private_api_available:
            return
        try:
            await self._http.post(
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_id)}/typing",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception as exc:
            logger.debug("iMessage start_typing failed for %s: %s", chat_id[:20], exc)

    async def stop_typing(self, chat_id: str) -> None:
        if not self._private_api_available:
            return
        try:
            await self._http.request(
                "DELETE",
                f"{self._api_url}/api/v1/chat/{quote_guid(chat_id)}/typing",
                params={"password": self._password},
                timeout=5.0,
            )
        except Exception as exc:
            logger.debug("iMessage stop_typing failed for %s: %s", chat_id[:20], exc)

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
            asyncio.create_task(self._mark_read(msg.chat_id))

    def verify_webhook_password(self, body: dict[str, object]) -> bool:
        """Verify BlueBubbles webhook password (timing-safe comparison)."""
        if not self._password:
            return True
        incoming = str(body.get("password", ""))
        return hmac.compare_digest(incoming, self._password)

    def _parse_message(self, data: dict[str, object]) -> InboundMessage | None:
        return parse_message(data, self._api_url, self._password, self._build_inbound)

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        chat_guid = msg.recipient_id or ""
        if not chat_guid:
            logger.warning("iMessage send: no recipient_id")
            return None

        last_guid: str | None = None
        reply_to_guid = msg.reply_to_id if msg.reply_to_id else None

        if msg.content:
            first_chunk = True
            for chunk in render(msg, self.render_style):
                quote_id = reply_to_guid if first_chunk else None
                guid = await self._send_text(chat_guid, chunk, reply_to=quote_id)
                if guid:
                    last_guid = guid
                first_chunk = False

        for attachment in msg.media:
            guid = await self._send_attachment(chat_guid, attachment)
            if guid:
                last_guid = guid

        return last_guid

    async def _send_text(
        self, chat_guid: str, text: str, *, reply_to: str | None = None
    ) -> str | None:
        """Send a text message. Returns message guid on success."""
        payload: dict[str, object] = {
            "chatGuid": chat_guid,
            "tempGuid": f"temp-{uuid.uuid4()}",
            "message": text,
        }
        if reply_to and self._private_api_available:
            payload["method"] = "private-api"
            payload["selectedMessageGuid"] = reply_to
            payload["partIndex"] = 0
        try:
            resp = await self._http.post(
                f"{self._api_url}/api/v1/message/text",
                params={"password": self._password},
                json=payload,
                timeout=SEND_TIMEOUT,
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
                timeout=MEDIA_TIMEOUT,
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

            config = MediaDownloadConfig(timeout_seconds=MEDIA_TIMEOUT)
            downloader = MediaDownloader(http_client=self._http, enable_default_cache=True)
            result = await downloader.download(att.url, config=config)
            if result.success and result.data:
                name = att.filename or filename_from_url(att.url)
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
        tapback = TAPBACK_MAP.get(emoji)
        if tapback is None:
            tapback = 2001
        if not emoji:
            tapback = tapback + 1000

        try:
            resp = await self._http.post(
                f"{self._api_url}/api/v1/message/react",
                params={"password": self._password},
                json={
                    "chatGuid": chat_id,
                    "selectedMessageGuid": message_id,
                    "reaction": tapback,
                },
                timeout=SEND_TIMEOUT,
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
