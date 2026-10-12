"""Signal channel — bidirectional messaging via Signal CLI REST API.

Inbound: WebSocket (preferred) or HTTP polling fallback → parse envelope → filter → emit
Outbound: REST API v2/send (text + base64 attachments)

Supports: DM/group, media send/receive, typing indicator,
reaction handling, mention parsing, edit-message detection.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.core.attachment_delivery::attempt_attachments (POS: per-attachment delivery with aggregated failure)
- .helpers::TypedDict structures, constants, _render_mentions (POS: types and pure functions)
- .inbound::SignalInboundMixin (POS: WebSocket / polling receive loops and envelope parsing)

[OUTPUT]
- SignalChannel: Signal CLI REST API bidirectional messaging Channel (credentials, lifecycle, outbound, groups, diagnostics); inbound comes from the mixin

[POS]
Signal integration. Implemented via Signal CLI REST API:
- Inbound: WebSocket ws:///v1/receive/{phone} (real-time), fallback HTTP polling
- Outbound: /v2/send (text + base64 attachments)
- Reactions: /v1/reactions
- Groups: /v1/groups
"""

from __future__ import annotations

import asyncio
import base64
import logging
from pathlib import Path

import httpx

from app.channels.core.attachment_delivery import attempt_attachments
from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.exceptions import ChannelSendError
from app.channels.core.mixins import CachedGroupMixin
from app.channels.providers.signal.api import SignalClient
from app.channels.providers.signal.helpers import (
    _MAX_TEXT_LENGTH,
    _SEND_TIMEOUT,
    _WS_PROBE_TIMEOUT,
)
from app.channels.providers.signal.inbound import SignalInboundMixin
from app.channels.reliability.reconnect import ConnectFn, reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    GroupInfo,
    IssueKind,
    IssueSeverity,
    MediaAttachment,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

logger = logging.getLogger(__name__)


class SignalChannel(SignalInboundMixin, BaseChannel, CachedGroupMixin):
    """Signal channel using Signal CLI REST API.

    Inbound messages are received via WebSocket (real-time, preferred) with
    automatic fallback to HTTP polling for older signal-cli-rest-api versions.
    """

    name = "signal"
    credential_spec = credential_spec(
        "signalCredentials",
        api_url=credential_field("apiUrl", "SIGNAL_API_URL"),
        phone_number=credential_field("phoneNumber", "SIGNAL_PHONE_NUMBER"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        media=True,
        file_upload=True,
        reactions=True,
        typing_indicator=True,
        typing_keepalive_interval=4.0,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="text",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    def __init__(
        self,
        api_url: str,
        phone_number: str,
        *,
        account_uuid: str = "",
        groups_cache_ttl: float = 300.0,
    ) -> None:
        BaseChannel.__init__(self)
        CachedGroupMixin.__init__(self, groups_cache_ttl=groups_cache_ttl)
        self._api_url = api_url.rstrip("/")
        self._phone = phone_number
        self._account_uuid = account_uuid
        self._api = SignalClient(api_url, phone_number)
        self._inbound_task: asyncio.Task[None] | None = None
        self._using_websocket = False
        self._bot_id = phone_number

    # ---- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        if not self._api_url or not self._phone:
            logger.info("Signal credentials not configured; channel idle")
            return
        self._status = ChannelStatus.RUNNING
        self._set_connected(True)

        connect_fn = await self._select_inbound_mode()
        self._inbound_task = asyncio.create_task(
            reconnect_loop(
                connect_fn,
                lambda: self._status,
                channel_name="SignalChannel",
            )
        )
        mode = "WebSocket" if self._using_websocket else "HTTP polling"
        logger.info("SignalChannel started (%s, inbound=%s)", self._phone, mode)

    async def _select_inbound_mode(self) -> ConnectFn:
        """Probe WebSocket endpoint and return the appropriate connect function.

        Attempts a short-lived WebSocket connection. If the server supports it,
        returns _ws_connect for real-time delivery. Otherwise falls back to
        _poll_once (HTTP polling every 2s).
        """
        try:
            from websockets.asyncio.client import connect

            async with asyncio.timeout(_WS_PROBE_TIMEOUT):
                async with connect(self._api.ws_url, close_timeout=2):
                    pass
            self._using_websocket = True
            logger.info("Signal: WebSocket available, using real-time mode")
            return self._ws_connect
        except Exception as exc:
            self._using_websocket = False
            logger.warning(
                "Signal: WebSocket probe failed (%s), falling back to HTTP polling",
                exc,
            )
            return self._poll_once

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._inbound_task:
            self._inbound_task.cancel()
            try:
                await self._inbound_task
            except asyncio.CancelledError:
                pass
        await self._api.close()

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
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

    async def list_groups(self, force_refresh: bool = False) -> list[GroupInfo]:
        if self._is_groups_cache_valid(force_refresh):
            return self._groups_cache.copy()
        try:
            raw_groups = await self._api.list_groups()
            groups: list[GroupInfo] = []
            for g in raw_groups:
                if not isinstance(g, dict):
                    continue
                gid = g.get("id") or g.get("internal_id", "")
                name = g.get("name", "")
                if gid:
                    groups.append(GroupInfo(jid=str(gid), name=str(name), channel=self.name))
            self._update_groups_cache(groups)
            return groups
        except Exception as exc:
            logger.warning("Signal list_groups failed: %s", exc)
            return []

    # ---- outbound ---------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send text and attachments through signal-cli; attachments ride with the first chunk.

        An attachment that cannot be encoded is reported after the rest went out, so the bus republishes
        only that attachment.
        """
        if not msg.recipient_id:
            raise ChannelSendError("Signal message has no recipient", channel=self.name, retriable=False)
        if not msg.content and not msg.media:
            return None

        attempts = await attempt_attachments(self.name, msg.media, self._encode_attachment)
        encoded = list(attempts.results)
        chunks = render(msg, self.render_style) if msg.content else ([""] if encoded else [])

        timestamp: str | None = None
        for index, chunk in enumerate(chunks):
            payload: dict[str, str | list[str]] = {
                "message": chunk,
                "number": self._phone,
                "recipients": [msg.recipient_id],
            }
            if index == 0 and encoded:
                payload["base64_attachments"] = encoded
            sent_at = await self._post_send(payload)
            timestamp = timestamp or sent_at

        attempts.raise_for_failures(self.name, delivered_any=bool(chunks))
        return timestamp

    async def _post_send(self, payload: dict[str, str | list[str]]) -> str | None:
        """POST one message to signal-cli and return its timestamp; raises ``ChannelSendError`` when it is not accepted."""
        try:
            resp = await self._api.send_message(payload)
        except httpx.HTTPError as exc:
            self.health.record_failure(f"send: {exc}")
            raise ChannelSendError(f"Signal request failed: {type(exc).__name__}", channel=self.name) from exc
        if resp.status_code != 201:
            self.health.record_failure(f"send: HTTP {resp.status_code}")
            raise ChannelSendError.from_http_status(self.name, resp.status_code)
        try:
            data = resp.json()
        except ValueError:
            return None
        timestamp = data.get("timestamp") if isinstance(data, dict) else None
        return str(timestamp) if timestamp else None

    async def _encode_attachment(self, att: MediaAttachment) -> str:
        """Encode an attachment as the base64 data URI signal-cli expects; raises ``ChannelSendError`` when it cannot be read."""
        if att.url:
            from app.channels.media import (
                MAX_FORWARD_DOWNLOAD_BYTES,
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(
                timeout_seconds=_SEND_TIMEOUT,
                max_size_bytes=MAX_FORWARD_DOWNLOAD_BYTES,
            )
            downloader = MediaDownloader(http_client=self._api._http, enable_default_cache=True)
            result = await downloader.download(att.url, config=config)
            if not result.success or not result.data:
                raise ChannelSendError(f"Signal could not download {att.display_name}", channel=self.name)
            raw_bytes = result.data
        elif att.path:
            try:
                raw_bytes = await asyncio.to_thread(Path(att.path).read_bytes)
            except OSError as exc:
                raise ChannelSendError(f"Signal cannot read {att.display_name}", channel=self.name, retriable=False) from exc
        else:
            raise ChannelSendError(f"Signal has no source for {att.display_name}", channel=self.name, retriable=False)

        if not raw_bytes:
            raise ChannelSendError(f"Signal attachment {att.display_name} is empty", channel=self.name, retriable=False)

        mime = att.mime_type or "application/octet-stream"
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        return f"data:{mime};filename={att.filename or 'file'};base64,{b64}"

    # ---- typing indicator -------------------------------------------------

    async def start_typing(self, chat_id: str) -> None:
        try:
            await self._api.start_typing(chat_id)
        except Exception as exc:
            logger.debug("Signal typing start failed for %s: %s", chat_id, exc)

    async def stop_typing(self, chat_id: str) -> None:
        try:
            await self._api.stop_typing()
        except Exception as exc:
            logger.debug("Signal typing stop failed for %s: %s", chat_id, exc)

    # ---- reaction ---------------------------------------------------------

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        try:
            ts = int(message_id) if message_id.isdigit() else 0
            await self._api.send_reaction(chat_id, emoji, chat_id, ts)
        except Exception as exc:
            logger.warning("Signal react failed (%s on %s): %s", emoji, message_id, exc)

    # ---- diagnostics ------------------------------------------------------

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._api_url or not self._phone:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Signal API URL or phone number not configured.",
                    fix="Set SIGNAL_API_URL and SIGNAL_PHONE_NUMBER, or configure in Settings → Channels → Signal.",
                )
            )
            return issues
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="Signal channel is in ERROR state.",
                )
            )
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        if self._status == ChannelStatus.RUNNING and not self._using_websocket:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.WARNING,
                    message="Signal: using HTTP polling (2s latency). WebSocket unavailable.",
                    fix="Upgrade signal-cli-rest-api for real-time message delivery via WebSocket.",
                )
            )
        return issues
