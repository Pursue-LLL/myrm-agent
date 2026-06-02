"""QQ channel — bidirectional messaging via QQ Bot Official API.

Inbound: WebSocket (primary) or HTTP webhook (fallback)
  - QQ WebSocket protocol: Hello→Identify→Ready→Heartbeat→Dispatch→Resume
  - Supports GROUP_AT_MESSAGE_CREATE, AT_MESSAGE_CREATE, C2C_MESSAGE_CREATE, DIRECT_MESSAGE_CREATE
Outbound: REST API (text/markdown + 2-step rich media upload)
  - msg_seq per-chat counter for multi-part replies
  - URL sanitization for group messages (domain dots → fullwidth period)

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.reliability.reconnect::reconnect_loop (POS: automatic reconnection)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- QQChannel: QQ Official Bot bidirectional messaging Channel (WebSocket + REST API)

[POS]
QQ Official Bot channel. WebSocket real-time event reception, REST API message sending,
2-step rich media upload, msg_seq multi-reply management, group chat URL sanitization.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    import websockets

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec, parse_bool
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    InboundMessage,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
    ToolSummaryDisplay,
)

from .api import QQClient
from .helpers import (
    is_group_event,
    is_supported_event,
    parse_attachments,
    parse_sender_id,
    sanitize_urls,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://api.sgroup.qq.com"
_SANDBOX_API = "https://sandbox.api.sgroup.qq.com"
_MAX_TEXT_LENGTH = 2000
_HEARTBEAT_TOLERANCE = 5.0

# QQ WebSocket intents
_INTENT_GROUP_AND_C2C = 1 << 25
_INTENT_DIRECT_MESSAGE = 1 << 12
_INTENT_PUBLIC_GUILD = 1 << 30
_DEFAULT_INTENTS = _INTENT_GROUP_AND_C2C | _INTENT_DIRECT_MESSAGE | _INTENT_PUBLIC_GUILD


class QQChannel(BaseChannel):
    """QQ Official Bot channel with WebSocket + REST API."""

    name = "qq"
    credential_spec = credential_spec(
        "qqCredentials",
        app_id=credential_field("appId", "QQ_APP_ID"),
        client_secret=credential_field("clientSecret", "QQ_CLIENT_SECRET"),
        sandbox=credential_field("sandbox", "QQ_SANDBOX", "false"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        buttons=False,
        quick_replies=False,
        select_menus=False,
        threads=False,
        edit=False,
        delete=False,
        reactions=False,
        typing_indicator=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        return cls(
            app_id=creds.get("app_id", ""),
            client_secret=creds.get("client_secret", ""),
            sandbox=parse_bool(creds.get("sandbox", "false")),
        )

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        *,
        sandbox: bool = False,
    ) -> None:
        super().__init__()
        self._app_id = app_id
        self._client_secret = client_secret
        self._sandbox = sandbox
        self._api_base = _SANDBOX_API if sandbox else _API_BASE
        self._api = QQClient(app_id, client_secret, self._api_base)

        # WebSocket state
        self._ws_task: asyncio.Task[None] | None = None
        self._session_id: str = ""
        self._last_seq: int | None = None

        # Per-chat state for passive replies
        self._chat_types: dict[str, str] = {}
        self._last_msg_ids: dict[str, str] = {}
        self._msg_seq_counters: dict[str, int] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self._app_id or not self._client_secret:
            logger.info("QQ Bot credentials not configured; channel idle")
            return
        try:
            await self._api.refresh_token()
        except Exception as exc:
            logger.warning("QQChannel: startup failed: %s", exc)
            self._status = ChannelStatus.ERROR
            return
        self._status = ChannelStatus.RUNNING
        self._ws_task = asyncio.create_task(
            reconnect_loop(
                self._ws_session_once,
                lambda: self._status,
                channel_name="QQChannel",
            )
        )
        logger.info("QQChannel: started (app_id=%s)", self._app_id)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._ws_task = None
        await self._api.close()
        logger.info("QQChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        try:
            return await self._api.health_check()
        except Exception:
            return False

    # ── Outbound ──────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        await self._api.ensure_token()
        chat_type = self._resolve_chat_type(msg)
        is_group = chat_type == "group"
        last_id: str | None = None

        for attachment in msg.media:
            mid = await self._api.send_media(
                msg.recipient_id,
                attachment,
                chat_type,
                self._last_msg_ids.get(msg.recipient_id),
                self._next_seq(msg.recipient_id),
            )
            if mid:
                last_id = mid

        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
                text = sanitize_urls(chunk) if is_group else chunk
                mid = await self._api.send_text(
                    msg.recipient_id,
                    text,
                    chat_type,
                    self._last_msg_ids.get(msg.recipient_id),
                    self._next_seq(msg.recipient_id),
                )
                if mid:
                    last_id = mid

        return last_id

    async def start_typing(self, chat_id: str) -> None:
        """Send QQ InputNotify (msg_type=6) typing indicator."""
        msg_id = self._last_msg_ids.get(chat_id)
        if not msg_id:
            return
        chat_type = self._chat_types.get(chat_id, "group")
        await self._api.send_typing(chat_id, chat_type, msg_id, self._next_seq(chat_id))

    # ── Webhook (fallback) ────────────────────────────────────────────

    async def handle_webhook(self, body: dict[str, object]) -> dict[str, object] | None:
        """Process a QQ Bot webhook callback (fallback when WebSocket unavailable)."""
        op = body.get("op")
        if op == 13:
            d = body.get("d", {})
            return {
                "op": 13,
                "d": {"plain_token": d.get("plain_token"), "event_ts": d.get("event_ts")},
            }

        event_type = str(body.get("t", ""))
        if is_supported_event(event_type):
            data = body.get("d", {})
            if isinstance(data, dict):
                msg = self._parse_event(event_type, data)
                if msg:
                    await self._emit_inbound(msg)

        return None

    # ── Diagnostics ───────────────────────────────────────────────────

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._app_id or not self._client_secret:
            missing = []
            if not self._app_id:
                missing.append("App ID")
            if not self._client_secret:
                missing.append("Client Secret")
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"{', '.join(missing)} not configured.",
                    fix="Set QQ_APP_ID and QQ_CLIENT_SECRET, or configure in Settings → Channels → QQ.",
                )
            )
            return issues
        if self.health.last_error:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message=self.health.last_error,
                )
            )
        return issues

    # ── WebSocket ─────────────────────────────────────────────────────

    async def _ws_session_once(self) -> None:
        """Single WebSocket session. reconnect_loop handles retry on failure."""
        import websockets

        await self._api.ensure_token()

        ws_url = await self._api.get_gateway_url()
        if not ws_url:
            raise RuntimeError("QQ gateway returned empty WebSocket URL")

        async with websockets.connect(ws_url) as ws:
            hello_raw = await ws.recv()
            hello = json.loads(hello_raw)
            if hello.get("op") != 10:
                raise RuntimeError(f"Expected Hello (op=10), got op={hello.get('op')}")

            heartbeat_interval = hello.get("d", {}).get("heartbeat_interval", 45000) / 1000.0

            if self._session_id and self._last_seq is not None:
                await ws.send(
                    json.dumps(
                        {
                            "op": 6,
                            "d": {
                                "token": f"QQBot {self._api._access_token}",
                                "session_id": self._session_id,
                                "seq": self._last_seq,
                            },
                        }
                    )
                )
            else:
                await ws.send(
                    json.dumps(
                        {
                            "op": 2,
                            "d": {
                                "token": f"QQBot {self._api._access_token}",
                                "intents": _DEFAULT_INTENTS,
                                "shard": [0, 1],
                            },
                        }
                    )
                )

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws, heartbeat_interval))
            try:
                async for raw in ws:
                    msg = json.loads(raw)
                    await self._handle_ws_message(msg)
            finally:
                self._set_connected(False)
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _heartbeat_loop(self, ws: websockets.ClientConnection, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.send(json.dumps({"op": 1, "d": self._last_seq}))
            except Exception:
                break

    async def _handle_ws_message(self, msg: dict[str, object]) -> None:
        op = msg.get("op")

        if op == 0:
            seq = msg.get("s")
            if isinstance(seq, int):
                self._last_seq = seq
            event_type = str(msg.get("t", ""))
            data = msg.get("d")

            if event_type == "READY" and isinstance(data, dict):
                self._session_id = str(data.get("session_id", ""))
                self._set_connected(True)
                logger.info("QQChannel: WebSocket ready (session=%s)", self._session_id)
                return

            if event_type == "RESUMED":
                self._set_connected(True)
                logger.info("QQChannel: WebSocket resumed")
                return

            if is_supported_event(event_type) and isinstance(data, dict):
                inbound = self._parse_event(event_type, data)
                if inbound:
                    await self._emit_inbound(inbound)

        elif op == 7:
            raise RuntimeError("Server requested reconnect (op=7)")

        elif op == 9:
            self._session_id = ""
            self._last_seq = None
            raise RuntimeError("Invalid session (op=9), will re-identify")

    # ── Event Parsing ─────────────────────────────────────────────────

    def _parse_event(self, event_type: str, data: dict[str, object]) -> InboundMessage | None:
        author = data.get("author")
        if not isinstance(author, dict):
            return None
        sender_id = parse_sender_id(author)
        if not sender_id:
            return None

        content = str(data.get("content", "")).strip()
        msg_id = str(data.get("id", ""))
        group_openid = str(data.get("group_openid", ""))
        channel_id = str(data.get("channel_id", "")) or group_openid

        is_group = is_group_event(event_type)
        mentioned = "AT_MESSAGE" in event_type
        chat_id = group_openid if is_group and group_openid else channel_id or sender_id

        raw_attachments = data.get("attachments")
        media_list = parse_attachments(raw_attachments) if isinstance(raw_attachments, list) else []

        if not content and not media_list:
            return None

        chat_type = "group" if is_group else "c2c"
        self._chat_types[chat_id] = chat_type
        self._last_msg_ids[chat_id] = msg_id
        self._msg_seq_counters[chat_id] = 1

        metadata: dict[str, object] = {
            "event_type": event_type,
            "msg_id": msg_id,
            "group_openid": group_openid,
            "chat_type": chat_type,
        }

        return self._build_inbound(
            sender_id=sender_id,
            content=content,
            chat_id=chat_id,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            metadata=metadata,
            message_id=msg_id,
        )

    # ── Send Helpers ──────────────────────────────────────────────────

    def _resolve_chat_type(self, msg: OutboundMessage) -> str:
        if msg.metadata:
            ct = msg.metadata.get("chat_type")
            if isinstance(ct, str) and ct:
                return ct
        return self._chat_types.get(msg.recipient_id, "group")

    def _next_seq(self, chat_id: str) -> int:
        seq = self._msg_seq_counters.get(chat_id, 1)
        self._msg_seq_counters[chat_id] = seq + 1
        return seq
