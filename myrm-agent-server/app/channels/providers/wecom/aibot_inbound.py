"""WeCom AI Bot inbound: WebSocket session, frame dispatch and inbound message / event parsing.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the host members the mixin calls)
- channels.reliability / websockets (POS: long-lived WebSocket transport to openws.work.weixin.qq.com)
- channels.types::InboundMessage, MediaAttachment, ReplyContext (POS: channel message value types)

[OUTPUT]
- WeComAiBotInboundMixin: _ws_session (subscribe + heartbeat + frame loop) and the callback parsers used by WeComAiBotChannel

[POS]
Inbound half of WeComAiBotChannel. The host owns credentials, stream state and outbound frames; the mixin only runs
the session and converts callbacks into InboundMessage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.types import (
    MediaAttachment,
    MediaType,
    ReplyContext,
)

if TYPE_CHECKING:
    import websockets

    from .aibot_channel import WeComStreamState

logger = logging.getLogger(__name__)

_WS_URL = "wss://openws.work.weixin.qq.com"
_HEARTBEAT_INTERVAL = 30.0


class WeComAiBotInboundMixin(BaseChannel):
    """WeCom AI Bot WebSocket session and inbound parsing for ``WeComAiBotChannel``.

    Requires the host class to provide the attributes below plus ``_emit_inbound`` / ``_build_inbound`` /
    ``_set_connected`` / ``health`` from ``BaseChannel``.
    """

    _bot_id: str
    _secret: str
    _ws: websockets.ClientConnection | None
    _heartbeat_task: asyncio.Task[None] | None
    _active_streams: dict[str, WeComStreamState]
    _group_req_ids: dict[str, str]

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
                # Mark active streams as force closed instead of clearing, allowing graceful completion via proactive delivery
                for stream_state in self._active_streams.values():
                    stream_state.is_force_closed = True
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
