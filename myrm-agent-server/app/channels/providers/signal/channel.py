"""Signal channel — bidirectional messaging via Signal CLI REST API.

Inbound: WebSocket (preferred) or HTTP polling fallback → parse envelope → filter → emit
Outbound: REST API v2/send (text + base64 attachments)

Supports: DM/group, media send/receive, typing indicator,
reaction handling, mention parsing, edit-message detection.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- .helpers::TypedDict structures, constants, _render_mentions (POS: types and pure functions)

[OUTPUT]
- SignalChannel: Signal CLI REST API bidirectional messaging Channel

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
import time
from pathlib import Path
from typing import cast

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.core.mixins import CachedGroupMixin
from app.channels.providers.signal.api import SignalClient
from app.channels.providers.signal.helpers import (
    _MAX_TEXT_LENGTH,
    _POLL_INTERVAL,
    _SEND_TIMEOUT,
    _WS_PROBE_TIMEOUT,
    _Attachment,
    _DataMessage,
    _Envelope,
    _Mention,
    _Reaction,
    _ReceivePayload,
    _render_mentions,
)
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
    guess_media_type,
)

logger = logging.getLogger(__name__)


class SignalChannel(BaseChannel, CachedGroupMixin):
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
        if not msg.recipient_id:
            logger.warning("Signal send: no recipient_id")
            return None
        try:
            if msg.media:
                return await self._send_with_attachments(msg)
            if msg.content:
                return await self._send_text(msg)
            return None
        except Exception as exc:
            logger.error("Signal send failed to %s: %s", msg.recipient_id, exc)
            self.health.record_failure(f"send: {exc}")
            return None

    async def _send_text(self, msg: OutboundMessage) -> str | None:
        chunks = render(msg, self.render_style)
        ts: str | None = None
        for chunk in chunks:
            payload: dict[str, str | list[str]] = {
                "message": chunk,
                "number": self._phone,
                "recipients": [msg.recipient_id],
            }
            resp = await self._api.send_message(payload)
            if resp.status_code == 201:
                if ts is None:
                    data = resp.json()
                    if isinstance(data, dict):
                        ts = str(data.get("timestamp", "")) or None
            else:
                logger.warning("Signal send text HTTP %s", resp.status_code)
        return ts

    async def _send_with_attachments(self, msg: OutboundMessage) -> str | None:
        """Send message with base64-encoded attachments via /v2/send."""
        b64_attachments: list[str] = []
        for att in msg.media:
            encoded = await self._encode_attachment(att)
            if encoded:
                b64_attachments.append(encoded)

        text = msg.content or ""
        if not text and not b64_attachments:
            return None

        chunks = render(msg, self.render_style) if text else [""]
        ts: str | None = None

        for i, chunk in enumerate(chunks):
            payload: dict[str, str | list[str]] = {
                "message": chunk,
                "number": self._phone,
                "recipients": [msg.recipient_id],
            }
            if i == 0 and b64_attachments:
                payload["base64_attachments"] = b64_attachments

            resp = await self._api.send_message(payload)
            if resp.status_code == 201:
                if ts is None:
                    data = resp.json()
                    if isinstance(data, dict):
                        ts = str(data.get("timestamp", "")) or None
            else:
                logger.warning("Signal send attachment HTTP %s", resp.status_code)
        return ts

    async def _encode_attachment(self, att: MediaAttachment) -> str | None:
        """Encode a MediaAttachment to base64 data URI for signal-cli REST API."""
        raw_bytes: bytes | None = None

        if att.url:
            from app.channels.media import (
                MediaDownloadConfig,
                MediaDownloader,
            )

            config = MediaDownloadConfig(timeout_seconds=_SEND_TIMEOUT)
            downloader = MediaDownloader(http_client=self._api._http, enable_default_cache=True)
            result = await downloader.download(att.url, config=config)
            if not result.success or not result.data:
                return None
            raw_bytes = result.data
        elif att.path:
            try:
                raw_bytes = await asyncio.to_thread(Path(att.path).read_bytes)
            except Exception as exc:
                logger.warning("Signal: failed to read attachment %s: %s", att.path, exc)
                return None

        if not raw_bytes:
            return None

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

    # ---- inbound: WebSocket (preferred) -----------------------------------

    async def _ws_connect(self) -> None:
        """Single WebSocket session — runs until connection drops."""
        async for payload in self._api.stream_events():
            if isinstance(payload, dict):
                await self._handle_envelope(cast(_ReceivePayload, payload))

    # ---- inbound: HTTP polling (fallback) ---------------------------------

    async def _poll_once(self) -> None:
        """Single poll cycle. reconnect_loop handles retry on failure."""
        while self._status == ChannelStatus.RUNNING:
            messages = await self._api.receive()
            for raw in messages:
                if isinstance(raw, dict):
                    await self._handle_envelope(cast(_ReceivePayload, raw))
            await asyncio.sleep(_POLL_INTERVAL)

    async def _handle_envelope(self, payload: _ReceivePayload) -> None:
        """Route an envelope to the appropriate handler."""
        envelope = payload.get("envelope")
        if not envelope or not isinstance(envelope, dict):
            return

        source = str(envelope.get("sourceNumber", "") or envelope.get("source", ""))
        if not source:
            return

        if self._is_self_message(envelope, source):
            return

        if "syncMessage" in envelope:
            return

        reaction = envelope.get("reactionMessage")
        if reaction and isinstance(reaction, dict):
            await self._handle_reaction(source, reaction)
            return

        data_msg = envelope.get("dataMessage")
        edit_msg = envelope.get("editMessage")

        if edit_msg and isinstance(edit_msg, dict):
            inner = edit_msg.get("dataMessage")
            if isinstance(inner, dict):
                target_ts = str(edit_msg.get("targetSentTimestamp", ""))
                await self._handle_data_message(envelope, source, inner, edit_target_ts=target_ts)
                return

        if data_msg and isinstance(data_msg, dict):
            dm_reaction = data_msg.get("reaction")
            if dm_reaction and isinstance(dm_reaction, dict):
                await self._handle_reaction(source, dm_reaction)
                return
            await self._handle_data_message(envelope, source, data_msg)

    def _is_self_message(self, envelope: _Envelope, source: str) -> bool:
        """Detect messages from our own account (phone or UUID)."""
        if source == self._phone:
            return True
        if self._account_uuid:
            source_uuid = envelope.get("sourceUuid", "")
            if source_uuid and source_uuid == self._account_uuid:
                return True
        return False

    async def _handle_reaction(self, source: str, reaction: _Reaction) -> None:
        """Emit a reaction event as an inbound message."""
        emoji = reaction.get("emoji", "")
        is_remove = reaction.get("isRemove", False)
        if not emoji or is_remove:
            return

        target_ts = str(reaction.get("targetSentTimestamp", ""))
        target_author = str(reaction.get("targetAuthor", ""))

        sent_at = time.time()
        if target_ts:
            try:
                sent_at = float(target_ts) / 1000.0
            except (ValueError, TypeError):
                pass

        msg = self._build_inbound(
            sender_id=source,
            content=emoji,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=target_author or source,
            is_group=False,
            mentioned=True,
            message_id=target_ts,
            metadata={"reaction": True, "target_message_id": target_ts},
        )
        await self._emit_inbound(msg)

    async def _handle_data_message(
        self,
        envelope: _Envelope,
        source: str,
        data_msg: _DataMessage,
        *,
        edit_target_ts: str = "",
    ) -> None:
        """Parse a dataMessage and emit as InboundMessage."""
        raw_text = str(data_msg.get("message", ""))
        mentions = data_msg.get("mentions")
        content = _render_mentions(raw_text, mentions if isinstance(mentions, list) else None)

        mentioned = self._check_mentioned(mentions)

        group_info = data_msg.get("groupInfo")
        is_group = bool(group_info) if isinstance(group_info, dict) else False
        chat_id = str(group_info.get("groupId", source)) if is_group and isinstance(group_info, dict) else source

        media_list = self._parse_attachments(data_msg.get("attachments"))

        if not content.strip() and not media_list:
            return

        ts = str(data_msg.get("timestamp", ""))

        metadata: dict[str, object] = {}
        if edit_target_ts:
            metadata["edit_target_ts"] = edit_target_ts
        if is_group and isinstance(group_info, dict):
            gname = group_info.get("groupName", "")
            if gname:
                metadata["group_name"] = gname

        reply_to_id: str | None = None
        quote = data_msg.get("quote")
        if isinstance(quote, dict):
            quote_id = quote.get("id")
            if quote_id is not None:
                reply_to_id = str(quote_id)

        sent_at = time.time()
        if ts:
            try:
                sent_at = float(ts) / 1000.0
            except (ValueError, TypeError):
                pass

        msg = self._build_inbound(
            sender_id=source,
            content=content.strip(),
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=chat_id,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            message_id=ts,
            reply_to_id=reply_to_id,
            metadata=metadata if metadata else {},
        )
        await self._emit_inbound(msg)

    def _check_mentioned(self, mentions: list[_Mention] | object | None) -> bool:
        """Check if any mention targets our phone number or account UUID."""
        if not isinstance(mentions, list):
            return False
        for m in mentions:
            if m.get("number") == self._phone:
                return True
            if self._account_uuid and m.get("uuid") == self._account_uuid:
                return True
        return False

    def _parse_attachments(self, attachments: list[_Attachment] | object | None) -> list[MediaAttachment]:
        if not isinstance(attachments, list):
            return []
        result: list[MediaAttachment] = []
        for att in attachments:
            if not isinstance(att, dict):
                continue
            ct = str(att.get("contentType", ""))
            fname = att.get("filename")
            att_id = att.get("id", "")
            mt = guess_media_type(fname or "file", ct)
            url = f"{self._api_url}/v1/attachments/{att_id}" if att_id else None
            result.append(
                MediaAttachment(
                    media_type=mt,
                    url=url,
                    filename=fname if isinstance(fname, str) else None,
                    mime_type=ct or None,
                )
            )
        return result
