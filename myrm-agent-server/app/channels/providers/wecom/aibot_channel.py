"""WeCom AI Bot channel — WebSocket long-connection with streaming replies.

Inbound: WebSocket frames (aibot_msg_callback / aibot_event_callback).
Outbound: aibot_respond_msg frames with stream support, aibot_send_msg for proactive push.

[INPUT]
- channels.core.base::BaseChannel (POS: Provides FileOperationObserver.)
- channels.providers.wecom.aibot_inbound::WeComAiBotInboundMixin (POS: WebSocket session and inbound parsing)
- channels.reliability.reconnect::reconnect_loop (POS: Reconnect loop with exponential backoff + jitter for long-lived connections.)

[OUTPUT]
- WeComAiBotChannel: WeCom AI Bot WebSocket longconnect Channel

[POS]
WeCom AI Bot channel: WebSocket long-lived connection, no public IP required,
native streaming replies. Supports message/event callbacks, welcome messages,
template cards, and proactive push.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import websockets

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    OutboundMessage,
    RenderStyle,
)
from app.channels.types.status import (
    ChannelIssue,
    IssueKind,
    IssueSeverity,
)

from .aibot_inbound import WeComAiBotInboundMixin

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 20000


@dataclass
class WeComStreamState:
    """State for a streaming WeCom AI Bot message."""

    stream_id: str
    chat_id: str
    req_id: str
    start_time: float = field(default_factory=time.time)
    last_update_time: float = field(default_factory=time.time)
    last_full_text: str = ""
    is_force_closed: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class WeComAiBotChannel(WeComAiBotInboundMixin, BaseChannel):
    """WeCom AI Bot channel using WebSocket long-connection.

    Connects to wss://openws.work.weixin.qq.com with bot_id + secret.
    Supports streaming replies, event callbacks, proactive messaging,
    and automatic reconnection with exponential backoff.
    """

    name = "wecom_aibot"
    credential_spec = credential_spec(
        "wecomAibotCredentials",
        bot_id=credential_field("botId", "WECOM_AIBOT_BOT_ID"),
        secret=credential_field("secret", "WECOM_AIBOT_SECRET"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        markdown=True,
        media=True,
        file_upload=True,
        edit=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="markdown",
        max_text_length=_MAX_TEXT_LENGTH,
    )

    def __init__(
        self,
        bot_id: str,
        secret: str,
    ) -> None:
        super().__init__()
        self._bot_id = bot_id
        self._secret = secret
        self._ws: websockets.ClientConnection | None = None
        self._ws_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._stream_guardian_task: asyncio.Task[None] | None = None
        self._active_streams: dict[str, WeComStreamState] = {}
        self._group_req_ids: dict[str, str] = {}

    # ── Lifecycle ──────────────────────────────────────────────

    async def start(self) -> None:
        if not self._bot_id or not self._secret:
            logger.info("WeComAiBot credentials not configured; channel idle")
            return
        self._status = ChannelStatus.RUNNING
        self._ws_task = asyncio.create_task(
            reconnect_loop(
                self._ws_session,
                lambda: self._status,
                channel_name="WeComAiBotChannel",
            )
        )
        self._stream_guardian_task = asyncio.create_task(self._stream_keepalive_loop())
        logger.info("WeComAiBotChannel: started")

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        if self._stream_guardian_task:
            self._stream_guardian_task.cancel()
            self._stream_guardian_task = None
        self._ws = None
        self._active_streams.clear()
        logger.info("WeComAiBotChannel: stopped")

    async def health_check(self) -> bool:
        if self._status not in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            return False
        return self._ws is not None and self.is_connected

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._bot_id:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Bot ID is not configured",
                    fix="Set WECOM_AIBOT_BOT_ID or configure in Settings → Channels → WeCom AI Bot",
                )
            )
        if not self._secret:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message="Secret is not configured",
                    fix="Set WECOM_AIBOT_SECRET or configure in Settings → Channels → WeCom AI Bot",
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

    # ── Outbound: send / placeholder / streaming ──────────────

    async def send(self, msg: OutboundMessage) -> str | None:
        if not self._ws:
            logger.warning("WeComAiBotChannel: no WebSocket connection, cannot send")
            return None

        req_id = str(msg.metadata.get("req_id", "")) if msg.metadata else ""
        chat_id = msg.recipient_id

        if msg.content:
            chunks = render(msg, self.render_style)
            if req_id and chunks:
                stream_id = uuid.uuid4().hex[:16]
                accumulated = ""
                for i, chunk in enumerate(chunks):
                    accumulated = f"{accumulated}\n{chunk}" if accumulated else chunk
                    is_final = i == len(chunks) - 1
                    await self._send_respond_msg(
                        req_id,
                        accumulated,
                        finish=is_final,
                        stream_id=stream_id,
                    )
            elif chunks:
                if not chat_id:
                    logger.warning("WeComAiBotChannel: no req_id or recipient_id, cannot send")
                    return None
                for chunk in chunks:
                    await self._send_proactive_msg(chat_id, chunk)
        return None

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        """Send a streaming placeholder and return the stream_id for later updates."""
        req_id = thread_id or ""
        if not req_id or not self._ws:
            return None
        stream_id = uuid.uuid4().hex[:16]

        self._active_streams[stream_id] = WeComStreamState(
            stream_id=stream_id, chat_id=chat_id, req_id=req_id, last_full_text=text
        )

        await self._send_respond_msg(req_id, text, finish=False, stream_id=stream_id)
        return stream_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Update a streaming message. message_id is the stream_id."""
        state = self._active_streams.get(message_id)
        if not state or not self._ws:
            return

        async with state.lock:
            if state.is_force_closed:
                state.last_full_text = text
                return

            await self._send_respond_msg(state.req_id, text, finish=False, stream_id=message_id)
            state.last_update_time = time.time()
            state.last_full_text = text

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Finalize a streaming message with the full content, handling multi-chunk pagination."""
        state = self._active_streams.pop(message_id, None)

        chunks = render(msg, self.render_style)
        if not chunks:
            chunks = [msg.content] if msg.content else []

        first_chunk = chunks[0] if chunks else ""
        overflow_chunks = chunks[1:] if len(chunks) > 1 else []

        if not state:
            # No active stream; send everything via proactive message
            for chunk in chunks:
                if chunk:
                    await self._send_proactive_msg(chat_id, chunk)
        elif state.is_force_closed:
            # Stream was closed by sentinel; deliver first chunk via respond_msg, rest proactive
            await self._send_respond_msg(state.req_id, first_chunk, finish=True)
            for chunk in overflow_chunks:
                if chunk:
                    await self._send_proactive_msg(chat_id, chunk)
        elif self._ws:
            # Active stream; morph first chunk in place, send remaining chunks proactively
            await self._send_respond_msg(state.req_id, first_chunk, finish=True, stream_id=message_id)
            for chunk in overflow_chunks:
                if chunk:
                    await self._send_proactive_msg(chat_id, chunk)

    # ── WebSocket session ─────────────────────────────────────

    async def _stream_keepalive_loop(self) -> None:
        """Global Sentinel: O(1) loop to manage active WeCom streams' keep-alive and hard limits."""
        try:
            while True:
                await asyncio.sleep(5.0)
                now = time.time()
                for stream_id, state in list(self._active_streams.items()):
                    if state.is_force_closed:
                        continue

                    async with state.lock:
                        if state.is_force_closed:
                            continue

                        total_duration = now - state.start_time
                        idle_duration = now - state.last_update_time

                        if total_duration > 3600.0:
                            logger.warning(f"WeComAiBot: Stream {stream_id} exceeded absolute TTL. Forcibly dropping.")
                            self._active_streams.pop(stream_id, None)
                            continue

                        if total_duration > 280.0:
                            fallback_suffix = "\n\n> *(处理时间较长，已转入后台运行，稍后推送最终结果)*"
                            safe_len = _MAX_TEXT_LENGTH - len(fallback_suffix)
                            safe_text = (
                                state.last_full_text[:safe_len] if len(state.last_full_text) > safe_len else state.last_full_text
                            )
                            fallback_text = safe_text + fallback_suffix

                            await self._send_respond_msg(state.req_id, fallback_text, finish=True, stream_id=stream_id)
                            state.is_force_closed = True
                            state.last_full_text = fallback_text
                        elif idle_duration > 20.0:
                            base_text = state.last_full_text or " 思考中..."
                            jitter = "\u200b" if int(now) % 2 == 0 else ""
                            text_to_send = base_text + jitter

                            await self._send_respond_msg(state.req_id, text_to_send, finish=False, stream_id=stream_id)
                            state.last_update_time = now
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("WeComAiBot stream guardian error: %s", exc)

    # ── Frame handling ────────────────────────────────────────

    # ── Outbound frame helpers ────────────────────────────────

    async def _send_frame(self, frame: dict[str, object]) -> None:
        """Send a JSON frame through the WebSocket."""
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps(frame))
        except Exception as exc:
            logger.debug("WeComAiBot send frame error: %s", exc)
            self.health.record_failure(str(exc))

    async def _send_respond_msg(
        self,
        req_id: str,
        content: str,
        *,
        finish: bool = True,
        stream_id: str | None = None,
    ) -> None:
        """Send aibot_respond_msg (streaming or final)."""
        sid = stream_id or uuid.uuid4().hex[:16]
        frame: dict[str, object] = {
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": req_id},
            "body": {
                "msgtype": "stream",
                "stream": {
                    "id": sid,
                    "finish": finish,
                    "content": content,
                },
            },
        }
        await self._send_frame(frame)

    async def _send_proactive_msg(
        self,
        chat_id: str,
        content: str,
        *,
        chat_type: int | None = None,
    ) -> None:
        """Send proactive message. Falls back to respond_msg for groups (API restriction)."""
        is_group = chat_id.startswith(("wr", "chat"))

        cached_req_id = self._group_req_ids.get(chat_id) if is_group else None
        if cached_req_id:
            await self._send_respond_msg(cached_req_id, content, finish=True)
            return

        if chat_type is None:
            chat_type = 1 if is_group else 0

        frame: dict[str, object] = {
            "cmd": "aibot_send_msg",
            "headers": {"req_id": uuid.uuid4().hex},
            "body": {
                "chatid": chat_id,
                "chat_type": chat_type,
                "msgtype": "text",
                "text": {"content": content},
            },
        }
        await self._send_frame(frame)
