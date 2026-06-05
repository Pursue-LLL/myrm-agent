"""WeCom AI Bot channel — WebSocket long-connection with streaming replies.

Inbound: WebSocket frames (aibot_msg_callback / aibot_event_callback).
Outbound: aibot_respond_msg frames with stream support, aibot_send_msg for proactive push.

[INPUT]
- channels.core.base::BaseChannel (POS: Provides FileOperationObserver.)
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
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ReplyContext,
)
from app.channels.types.status import (
    ChannelIssue,
    IssueKind,
    IssueSeverity,
)

logger = logging.getLogger(__name__)

_WS_URL = "wss://openws.work.weixin.qq.com"
_HEARTBEAT_INTERVAL = 30.0
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


class WeComAiBotChannel(BaseChannel):
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
        """Finalize a streaming message with the full content."""
        state = self._active_streams.pop(message_id, None)

        chunks = render(msg, self.render_style)
        final_content = "\n".join(chunks) if chunks else msg.content

        if not state:
            await self._send_proactive_msg(chat_id, final_content)
        elif state.is_force_closed:
            await self._send_respond_msg(state.req_id, final_content, finish=True)
        elif self._ws:
            await self._send_respond_msg(state.req_id, final_content, finish=True, stream_id=message_id)

    # ── WebSocket session ─────────────────────────────────────

    async def _ws_session(self) -> None:
        """Single WebSocket session. reconnect_loop handles retry on failure."""
        import websockets

        async with websockets.connect(_WS_URL) as ws:
            self._ws = ws

            subscribed = await self._subscribe(ws)
            if not subscribed:
                self._ws = None
                raise ConnectionError("WeComAiBot: subscription failed")

            self._set_connected(True)
            self.health.record_success()

            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

            try:
                async for raw in ws:
                    try:
                        frame = json.loads(raw)
                        await self._handle_frame(frame)
                    except json.JSONDecodeError:
                        logger.debug("WeComAiBot: non-JSON frame ignored")
            finally:
                self._set_connected(False)
                self._ws = None
                self._active_streams.clear()
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None

    async def _subscribe(self, ws: websockets.ClientConnection) -> bool:
        """Send aibot_subscribe and verify response."""
        req_id = uuid.uuid4().hex
        frame = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": req_id},
            "body": {
                "bot_id": self._bot_id,
                "secret": self._secret,
            },
        }
        await ws.send(json.dumps(frame))

        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            resp = json.loads(raw)
            ret_code = resp.get("body", {}).get("ret_code", -1)
            if ret_code == 0:
                logger.info("WeComAiBotChannel: subscribed successfully")
                return True
            logger.warning(
                "WeComAiBot subscribe failed: ret_code=%s, ret_msg=%s",
                ret_code,
                resp.get("body", {}).get("ret_msg", ""),
            )
            return False
        except TimeoutError:
            logger.warning("WeComAiBot subscribe timeout")
            return False

    async def _heartbeat_loop(self, ws: websockets.ClientConnection) -> None:
        """Periodic ping to keep the WebSocket alive."""
        try:
            while True:
                await asyncio.sleep(_HEARTBEAT_INTERVAL)
                ping_frame = json.dumps({"cmd": "ping"})
                await ws.send(ping_frame)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("WeComAiBot heartbeat error: %s", exc)

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

    async def _handle_frame(self, frame: dict[str, object]) -> None:
        """Dispatch incoming WebSocket frames by cmd type."""
        cmd = frame.get("cmd", "")
        if cmd == "aibot_msg_callback":
            await self._handle_msg_callback(frame)
        elif cmd == "aibot_event_callback":
            await self._handle_event_callback(frame)
        elif cmd == "pong" or cmd == "aibot_subscribe":
            pass
        else:
            logger.debug("WeComAiBot: unhandled cmd=%s", cmd)

    async def _handle_msg_callback(self, frame: dict[str, object]) -> None:
        """Process an incoming message callback."""
        headers = frame.get("headers", {})
        body = frame.get("body", {})
        if not isinstance(headers, dict) or not isinstance(body, dict):
            return

        req_id = str(headers.get("req_id", ""))
        msg_id = str(body.get("msgid", ""))
        chat_type = str(body.get("chattype", "single"))
        chat_id = str(body.get("chatid", ""))
        from_info = body.get("from", {})
        sender_id = str(from_info.get("userid", "")) if isinstance(from_info, dict) else ""

        is_group = chat_type == "group"
        if not is_group:
            chat_id = sender_id

        if is_group and req_id and chat_id:
            self._group_req_ids[chat_id] = req_id
            if len(self._group_req_ids) > 500:
                oldest = next(iter(self._group_req_ids))
                del self._group_req_ids[oldest]

        content, media = self._parse_msg_content(body)
        if not content and not media:
            return

        reply_to = self._parse_quoted_message(body)

        metadata: dict[str, object] = {"req_id": req_id}

        msg = self._build_inbound(
            sender_id=sender_id,
            content=content,
            chat_id=chat_id,
            is_group=is_group,
            mentioned=True,
            media=tuple(media),
            metadata=metadata,
            message_id=msg_id,
            thread_id=req_id or None,
            reply_to=reply_to,
        )
        await self._emit_inbound(msg)

    def _parse_msg_item(self, item: dict[str, object]) -> tuple[str, MediaAttachment | None]:
        """Parse a single message item (for both primary messages and quotes).

        Returns: (text_content, media_attachment) tuple.
        """
        msg_type = str(item.get("msgtype", ""))
        content = ""
        media = None

        if msg_type == "text":
            text_body = item.get("text", {})
            content = str(text_body.get("content", "")) if isinstance(text_body, dict) else ""
        elif msg_type == "image":
            img_body = item.get("image", {})
            if isinstance(img_body, dict):
                url = str(img_body.get("url", ""))
                media = MediaAttachment(media_type=MediaType.IMAGE, url=url or None)
        elif msg_type == "file":
            file_body = item.get("file", {})
            if isinstance(file_body, dict):
                filename = str(file_body.get("filename", ""))
                media = MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    filename=filename or None,
                )
        elif msg_type == "voice":
            media = MediaAttachment(media_type=MediaType.AUDIO)
        elif msg_type == "video":
            media = MediaAttachment(media_type=MediaType.VIDEO)
        elif msg_type == "location":
            loc = item.get("location", {})
            if isinstance(loc, dict):
                lat = loc.get("latitude", "")
                lng = loc.get("longitude", "")
                label = str(loc.get("label", ""))
                content = f"[Location] {label} ({lat}, {lng})" if label else f"[Location] ({lat}, {lng})"
        elif msg_type == "link":
            link = item.get("link", {})
            if isinstance(link, dict):
                title = str(link.get("title", ""))
                url = str(link.get("url", ""))
                content = f"[Link] {title}: {url}" if title else f"[Link] {url}"

        return content.strip(), media

    def _parse_msg_content(self, body: dict[str, object]) -> tuple[str, list[MediaAttachment]]:
        """Extract Text content and media from a message callback body."""
        content, media_item = self._parse_msg_item(body)
        media = [media_item] if media_item else []
        return content, media

    def _parse_quoted_message(self, body: dict[str, object]) -> ReplyContext | None:
        """Parse quoted/replied-to message from WeCom callback body.

        Supports: text, image, file, voice, video, location, link, mixed quote types.
        Returns: ReplyContext with structured quote content and media.
        """
        quote = body.get("quote")
        if not quote or not isinstance(quote, dict):
            return None

        quote_type = str(quote.get("msgtype", ""))
        if not quote_type:
            return None

        if quote_type == "mixed":
            quoted_items = quote.get("mixed", {})
            if isinstance(quoted_items, dict):
                quoted_items = quoted_items.get("msg_item", [])
            quoted_items = quoted_items if isinstance(quoted_items, list) else []
        else:
            quoted_items = [quote]

        if not quoted_items:
            return None

        text_parts: list[str] = []
        media_list: list[MediaAttachment] = []
        quoted_msg_id = str(quote.get("msgid", ""))

        for q_item in quoted_items:
            content, media = self._parse_msg_item(q_item)
            if content:
                text_parts.append(content)
            if media:
                media_list.append(media)

        if not text_parts and not media_list:
            return None

        content = "\n".join(text_parts)
        return ReplyContext(
            message_id=quoted_msg_id or "unknown",
            content=content,
            media=tuple(media_list),
            sender_id=None,
            sender_name=None,
            timestamp=None,
        )

    async def _handle_event_callback(self, frame: dict[str, object]) -> None:
        """Process event callbacks (enter_chat, template_card_event, etc.)."""
        headers = frame.get("headers", {})
        body = frame.get("body", {})
        if not isinstance(headers, dict) or not isinstance(body, dict):
            return

        req_id = str(headers.get("req_id", ""))
        event = body.get("event", {})
        if not isinstance(event, dict):
            return

        event_type = str(event.get("eventtype", ""))

        if event_type == "enter_chat":
            from_info = body.get("from", {})
            sender_id = str(from_info.get("userid", "")) if isinstance(from_info, dict) else ""
            if sender_id and req_id:
                msg = self._build_inbound(
                    sender_id=sender_id,
                    content="",
                    chat_id=sender_id,
                    is_group=False,
                    mentioned=True,
                    metadata={"req_id": req_id, "event_type": "enter_chat"},
                    message_id=str(body.get("msgid", "")),
                    thread_id=req_id,
                )
                await self._emit_inbound(msg)

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
