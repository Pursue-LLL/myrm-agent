"""OneBot v11 Channel Provider (Reverse WebSocket).

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types.messages::InboundMessage, (POS: Core message type definitions. All cross-channel communication data structures are defined here; zero I/O, pure data.)
- channels.types.status::ChannelCapabilities (POS: Channel status and diagnostic type definitions. Used for Gateway health checks, issue collection, and capability negotiation.)
- channels.providers.onebot.helpers::parse_onebot_message, build_onebot_message (POS: OneBot message converters)

[OUTPUT]
- OneBotChannel: OneBot v11 channel implementation class

[POS]
OneBot v11 channel adapter. Runs as a WebSocket Reverse Server, accepting connections from
clients like NapCatQQ and go-cqhttp, enabling QQ personal/group message send/receive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Self

import websockets

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec
from app.channels.providers.onebot.helpers import (
    build_onebot_message,
    parse_onebot_message,
)
from app.channels.types.messages import (
    OutboundMessage,
    ReasoningDisplay,
    RenderStyle,
    ReplyContext,
    ToolSummaryDisplay,
)
from app.channels.types.status import ChannelCapabilities, ChannelStatus

logger = logging.getLogger(__name__)


class OneBotChannel(BaseChannel):
    """OneBot v11 Channel implementation (Reverse WebSocket Server).

    Acts as a WebSocket server that OneBot clients (like NapCatQQ) connect to.
    Supports:
    - Private and Group messages
    - Media receiving and sending (Images, Audio, Video)
    - Replies and Mentions
    """

    name = "onebot"

    credential_spec = credential_spec(
        "onebotCredentials",
        host=credential_field(
            "host",
            "ONEBOT_HOST",
            default="0.0.0.0",
            required=True,
            is_sensitive=False,
            help_text="OneBot WebSocket Service器Address / OneBot WebSocket server host",
        ),
        port=credential_field(
            "port",
            "ONEBOT_PORT",
            default="3001",
            required=True,
            is_sensitive=False,
            help_text="OneBot WebSocket Service器Port / OneBot WebSocket server port",
            validator=lambda v: str(int(v)),  # Validate port is a valid integer
        ),
        access_token=credential_field(
            "accessToken",
            "ONEBOT_ACCESS_TOKEN",
            default="",
            required=False,
            is_sensitive=True,
            help_text="OneBot 访问Token（optional）/ OneBot access token (optional)",
        ),
    )

    capabilities = ChannelCapabilities(
        text=True,
        markdown=False,  # OneBot doesn't natively support markdown rendering
        media=True,
        voice_message=True,
        file_upload=False,
        buttons=False,
        quick_replies=False,
        select_menus=False,
        threads=False,
        edit=False,
        delete=True,
        reactions=False,
        typing_indicator=False,
        max_text_length=4000,
    )

    render_style = RenderStyle(
        format="plaintext",
        max_text_length=4000,
        reasoning_display=ReasoningDisplay.INLINE,
        tool_summary_display=ToolSummaryDisplay.COMPACT,
    )

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        return cls(
            host=creds.get("host", "0.0.0.0"),
            port=int(creds.get("port", "3001")),
            access_token=creds.get("access_token", ""),
        )

    def __init__(self, host: str = "0.0.0.0", port: int = 3001, access_token: str = "") -> None:
        super().__init__()
        self._host = host
        self._port = port
        self._access_token = access_token

        self._server: websockets.server.WebSocketServer | None = None
        self._active_ws: websockets.server.WebSocketServerProtocol | None = None
        self._pending_requests: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._bot_id: str = ""

        # Auto-reconnect state
        self._reconnect_task: asyncio.Task[None] | None = None
        self._should_reconnect = False
        self._reconnect_delay = 1.0  # Initial delay in seconds
        self._max_reconnect_delay = 60.0  # Max delay in seconds

    async def start(self) -> None:
        """Start the WebSocket Reverse Server with auto-reconnect."""
        await super().start()
        self._should_reconnect = True
        self._reconnect_delay = 1.0

        try:
            self._server = await websockets.serve(
                self._ws_handler,
                self._host,
                self._port,
            )
            logger.info("OneBotChannel: Reverse WebSocket server listening on ws://%s:%s", self._host, self._port)
            self._status = ChannelStatus.RUNNING
        except Exception as e:
            logger.error("OneBotChannel: Failed to start server: %s", e)
            self.health.record_failure(str(e))
            self._status = ChannelStatus.ERROR

            # Start reconnect loop if initial start failed
            if self._should_reconnect and not self._reconnect_task:
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Auto-reconnect loop with exponential backoff."""
        while self._should_reconnect:
            await asyncio.sleep(self._reconnect_delay)

            if not self._should_reconnect:
                break

            try:
                logger.info("OneBotChannel: Attempting to reconnect... (delay: %ss)", self._reconnect_delay)
                self._server = await websockets.serve(
                    self._ws_handler,
                    self._host,
                    self._port,
                )
                logger.info("OneBotChannel: Reconnected successfully")
                self._status = ChannelStatus.RUNNING
                self._reconnect_delay = 1.0  # Reset delay on success
                self.health.record_success()
                break  # Exit loop on successful reconnect
            except Exception as e:
                logger.warning("OneBotChannel: Reconnect failed: %s", e)
                self.health.record_failure(str(e))

                # Exponential backoff: double the delay up to max
                self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    async def stop(self) -> None:
        """Stop the WebSocket server and disable auto-reconnect."""
        await super().stop()
        self._should_reconnect = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._active_ws:
            await self._active_ws.close()
        self._active_ws = None
        self._set_connected(False)

    async def health_check(self) -> bool:
        """Check if the server is running and a client is connected."""
        is_alive = self._server is not None and self._server.is_serving()
        if not is_alive:
            self.health.record_failure("WebSocket server is not running")
            return False

        if not self._active_ws or self._active_ws.closed:
            # Server is running but no client connected yet. We consider this "idle" but healthy enough
            self.health.record_success()
            return True

        self.health.record_success()
        return True

    async def _ws_handler(self, websocket: websockets.server.WebSocketServerProtocol) -> None:
        """Handle incoming WebSocket connections from OneBot clients."""
        # 1. Authentication
        if self._access_token:
            auth_header = websocket.request_headers.get("Authorization", "")
            expected = f"Bearer {self._access_token}"
            if auth_header != expected:
                logger.warning("OneBotChannel: Client authentication failed")
                await websocket.close(1008, "Authentication failed")
                return

        # 2. Connection accepted
        logger.info("OneBotChannel: Client connected from %s", websocket.remote_address)

        # If there's already an active connection, close it (we only support one bot per port for now)
        if self._active_ws and not self._active_ws.closed:
            logger.warning("OneBotChannel: Closing previous connection")
            await self._active_ws.close()

        self._active_ws = websocket
        self._set_connected(True)

        # 3. Message loop
        try:
            async for message in websocket:
                if isinstance(message, str):
                    await self._handle_raw_message(message)
        except websockets.exceptions.ConnectionClosed:
            logger.info("OneBotChannel: Client disconnected")
        except Exception as e:
            logger.error("OneBotChannel: Error in WebSocket loop: %s", e)
        finally:
            if self._active_ws == websocket:
                self._active_ws = None
                self._set_connected(False)

                # Trigger reconnect if server is still supposed to be running
                if self._should_reconnect and not self._reconnect_task:
                    logger.info("OneBotChannel: Starting auto-reconnect...")
                    self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _handle_raw_message(self, raw: str) -> None:
        """Parse and route incoming JSON messages."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # 1. Handle API Responses (echo)
        if "echo" in data:
            echo = data["echo"]
            if echo in self._pending_requests:
                fut = self._pending_requests.pop(echo)
                if not fut.done():
                    fut.set_result(data)
            return

        # 2. Handle Events (post_type)
        post_type = data.get("post_type")

        if post_type == "meta_event":
            meta_event_type = data.get("meta_event_type")
            if meta_event_type == "lifecycle" and data.get("sub_type") == "connect":
                self._bot_id = str(data.get("self_id", ""))
                logger.info("OneBotChannel: Bot %s connected", self._bot_id)
            elif meta_event_type == "heartbeat":
                # Keep connection alive
                pass

        elif post_type == "message":
            await self._handle_message_event(data)

        elif post_type == "notice":
            # Handle group invites, friend requests, etc. if needed
            pass

    async def _handle_message_event(self, data: dict[str, object]) -> None:
        """Convert OneBot message event to InboundMessage."""
        message_type = data.get("message_type")  # "private" or "group"
        is_group = message_type == "group"

        sender_info = data.get("sender", {})
        sender_id = str(sender_info.get("user_id", ""))
        sender_name = sender_info.get("nickname") or sender_info.get("card")

        chat_id = str(data.get("group_id", "")) if is_group else sender_id
        message_id = str(data.get("message_id", ""))

        # Parse content and media
        raw_message = data.get("message", [])
        text, media = parse_onebot_message(raw_message)

        # Check mentions and replies
        mentioned = False
        reply_to = None

        if isinstance(raw_message, list):
            for seg in raw_message:
                if seg.get("type") == "at" and str(seg.get("data", {}).get("qq")) == self._bot_id:
                    mentioned = True
                elif seg.get("type") == "reply":
                    # OneBot doesn't always provide full quoted message content in the event,
                    # we just store the ID for now.
                    reply_to = ReplyContext(
                        message_id=str(seg.get("data", {}).get("id", "")),
                        content="",  # We don't have the content without an extra API call
                    )

        # In private chats, you are always "mentioned" implicitly
        if not is_group:
            mentioned = True

        inbound_msg = self._build_inbound(
            sender_id=sender_id,
            content=text,
            chat_id=chat_id,
            sender_name=sender_name,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media),
            message_id=message_id,
            reply_to=reply_to,
        )

        await self._emit_inbound(inbound_msg)

    async def _call_api(self, action: str, params: dict[str, object], timeout: float = 10.0) -> dict[str, object]:
        """Call a OneBot API endpoint and wait for response."""
        if not self._active_ws or self._active_ws.closed:
            raise RuntimeError("No OneBot client connected")

        echo = uuid.uuid4().hex
        payload = {"action": action, "params": params, "echo": echo}

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, object]] = loop.create_future()
        self._pending_requests[echo] = fut

        await self._active_ws.send(json.dumps(payload))

        try:
            response = await asyncio.wait_for(fut, timeout=timeout)
            if response.get("status") == "failed":
                logger.error("OneBot API error (%s): %s", action, response)
            return response
        except TimeoutError:
            self._pending_requests.pop(echo, None)
            logger.error("OneBot API timeout: %s", action)
            raise

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send a message via OneBot API with automatic fragmentation for long messages."""
        if not self._active_ws or self._active_ws.closed:
            logger.error("OneBotChannel: Cannot send message, no client connected")
            return None

        # Determine if it's a group or private message
        is_group = False
        if msg.metadata and msg.metadata.get("is_group") is True:
            is_group = True
        elif len(msg.recipient_id) < 11:
            pass

        # Check if message needs fragmentation (>4000 chars)
        if msg.content and len(msg.content) > 4000:
            return await self._send_fragmented(msg, is_group)

        # Send single message
        action = "send_group_msg" if is_group else "send_private_msg"
        params: dict[str, object] = {
            "group_id" if is_group else "user_id": int(msg.recipient_id),
            "message": build_onebot_message(msg),
        }

        try:
            response = await self._call_api(action, params)
            data = response.get("data", {})
            return str(data.get("message_id")) if data else None
        except Exception as e:
            logger.error("Failed to send OneBot message: %s", e)
            self.health.record_failure(str(e))
            return None

    async def _send_fragmented(self, msg: OutboundMessage, is_group: bool) -> str | None:
        """Send a long message by fragmenting it into multiple parts."""
        content = msg.content or ""
        fragment_size = 3500  # Leave buffer for overhead
        fragments = [content[i : i + fragment_size] for i in range(0, len(content), fragment_size)]

        logger.info("OneBotChannel: Fragmenting long message into %d parts", len(fragments))

        action = "send_group_msg" if is_group else "send_private_msg"
        last_message_id = None

        for i, fragment in enumerate(fragments, 1):
            # Create fragment message
            fragment_msg = OutboundMessage(
                content=f"[{i}/{len(fragments)}] {fragment}" if len(fragments) > 1 else fragment,
                recipient_id=msg.recipient_id,
                media=msg.media if i == 1 else (),  # Only send media with first fragment
                metadata=msg.metadata,
            )

            params: dict[str, object] = {
                "group_id" if is_group else "user_id": int(msg.recipient_id),
                "message": build_onebot_message(fragment_msg),
            }

            try:
                response = await self._call_api(action, params)
                data = response.get("data", {})
                last_message_id = str(data.get("message_id")) if data else None

                # Small delay between fragments to avoid rate limiting
                if i < len(fragments):
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("Failed to send OneBot message fragment %d/%d: %s", i, len(fragments), e)
                self.health.record_failure(str(e))
                break

        return last_message_id

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Recall a message."""
        try:
            await self._call_api("delete_msg", {"message_id": int(message_id)})
        except Exception as e:
            logger.warning("Failed to delete OneBot message: %s", e)
