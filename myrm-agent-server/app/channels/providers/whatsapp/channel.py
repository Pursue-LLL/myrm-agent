"""WhatsApp channel — bidirectional messaging via Baileys Node.js bridge.

Python ↔ Node.js IPC via JSON Lines over stdin/stdout.
DM + group messages, LID→PN resolution, mention/reply-to-bot detection.

[INPUT]
- channels.core.base::BaseChannel, (POS: Provides FileOperationObserver.)

[OUTPUT]
- WhatsAppChannel: WhatsApp Web bidirectional communication Channel (Baileys 7.x bridge)

[POS]
WhatsApp integration: inbound bridge->_handle_inbound->_emit_inbound, outbound bridge stdin "send".
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from app.channels.core.allow_policy import OPEN_POLICY
from app.channels.core.base import BaseChannel
from app.channels.core.mixins import CachedGroupMixin
from app.channels.core.rate_limit import DEFAULT_RATE_LIMIT
from app.channels.protocols.async_login import (
    LoginEvent,
    LoginMethod,
    LoginState,
    LoginStatus,
)
from app.channels.providers.whatsapp.bridge import BridgeProcessMixin
from app.channels.providers.whatsapp.helpers import (
    _MAX_TEXT_LENGTH,
    _default_auth_dir,
    _normalize_jid,
    _prefer_pn_jid,
    _strip_device_suffix,
    check_mentioned,
    is_self_chat,
    parse_message_key,
)
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    GroupInfo,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
    ReplyContext,
    StartMode,
)

logger = logging.getLogger(__name__)


class WhatsAppChannel(BaseChannel, CachedGroupMixin, BridgeProcessMixin):
    """WhatsApp Web channel via Node.js Baileys bridge subprocess.

    Lifecycle:
    1. ``start()`` → ensure npm deps → spawn bridge subprocess → QR or auto-login
    2. Bridge stdout "message" events → ``_emit_inbound``
    3. ``send()`` → write JSON Line to bridge stdin
    4. ``stop()`` → send "stop" command → terminate subprocess
    """

    name = "whatsapp"
    allow_policy = OPEN_POLICY
    rate_limit_config = DEFAULT_RATE_LIMIT
    supported_login_methods = [LoginMethod.QR_CODE]
    start_mode = StartMode.ON_DEMAND
    capabilities = ChannelCapabilities(
        text=True,
        markdown=False,
        media=True,
        voice_message=True,
        file_upload=True,
        buttons=False,
        quick_replies=False,
        edit=True,
        delete=True,
        reactions=True,
        typing_indicator=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(
        format="whatsapp",
        max_text_length=_MAX_TEXT_LENGTH,
        supports_code_fence=True,
        supports_links=True,
        app_name_prefix="[Myrm AI]",
    )

    def should_auto_start(self) -> bool:
        """Auto-start only when a persisted Baileys session exists."""
        return (self._auth_dir / "creds.json").exists()

    def __init__(self, auth_dir: str | None = None, groups_cache_ttl: float = 300.0) -> None:
        BaseChannel.__init__(self)
        CachedGroupMixin.__init__(self, groups_cache_ttl=groups_cache_ttl)
        self._auth_dir = Path(auth_dir) if auth_dir else _default_auth_dir()
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = asyncio.Event()
        self._qr_code: str | None = None
        self._self_jid: str | None = None
        self._groups_future: asyncio.Future[list[dict[str, str]]] | None = None
        self._sent_futures: dict[str, asyncio.Future[dict[str, object]]] = {}
        self._media_download_futures: dict[str, asyncio.Future[str]] = {}
        self._lid_to_pn: dict[str, str] = {}

    @property
    def qr_code(self) -> str | None:
        """Current QR code string for pairing (None if already paired)."""
        return self._qr_code

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    def _set_connected(self, connected: bool) -> None:
        was_connected = self._connected.is_set()
        if connected:
            self._connected.set()
        else:
            self._connected.clear()
        if was_connected != connected:
            self.emit("connection_change", {"connected": connected})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn the Baileys bridge subprocess."""
        try:
            await self._ensure_node_deps()
            await self._spawn_bridge()
            self._status = ChannelStatus.RUNNING
            logger.info("WhatsAppChannel: started (auth_dir=%s)", self._auth_dir)
        except Exception as e:
            self._status = ChannelStatus.ERROR
            logger.warning("WhatsAppChannel: failed to start: %s", e)
            raise

    async def stop(self) -> None:
        """Send stop command and terminate the bridge subprocess."""
        self._status = ChannelStatus.STOPPED

        if self._process and self._process.stdin:
            try:
                self._write_cmd({"type": "stop"})
            except (BrokenPipeError, ConnectionResetError):
                pass

        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        await self._kill_process()
        self._set_connected(False)
        logger.info("WhatsAppChannel: stopped")

    async def health_check(self) -> bool:
        if self._process is None or self._process.returncode is not None:
            return False
        return self._status == ChannelStatus.RUNNING

    # ------------------------------------------------------------------
    # Outbound messaging
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str | None:
        """Send a message (media + text) to a WhatsApp user via the bridge.

        Returns the platform message key (JSON) of the last text chunk sent,
        or None if only media was sent.
        """
        if not self._process or not self._connected.is_set():
            raise RuntimeError("WhatsAppChannel not connected")

        jid = _normalize_jid(msg.recipient_id)
        last_key: str | None = None

        for attachment in msg.media:
            self._send_media(jid, attachment)

        if msg.content:
            chunks = list(render(msg, self.render_style))
            for chunk in chunks:
                nonce = uuid.uuid4().hex[:12]
                loop = asyncio.get_running_loop()
                fut: asyncio.Future[dict[str, object]] = loop.create_future()
                self._sent_futures[nonce] = fut
                self._write_cmd({"type": "send", "to": jid, "text": chunk, "nonce": nonce})
                try:
                    key = await asyncio.wait_for(fut, timeout=10.0)
                    last_key = json.dumps(key)
                except TimeoutError:
                    self._sent_futures.pop(nonce, None)

        logger.warning("WhatsAppChannel: sent to %s (media=%d)", jid, len(msg.media))
        return last_key

    def _send_media(self, jid: str, attachment: MediaAttachment) -> None:
        """Write a send_media command to the bridge for a single attachment."""
        cmd: dict[str, str] = {
            "type": "send_media",
            "to": jid,
            "media_type": attachment.media_type.value,
        }
        if attachment.url:
            cmd["url"] = attachment.url
        elif attachment.path:
            cmd["path"] = attachment.path
        if attachment.filename:
            cmd["filename"] = attachment.filename
        if attachment.mime_type:
            cmd["mimetype"] = attachment.mime_type
        if attachment.caption:
            cmd["caption"] = attachment.caption
        self._write_cmd(cmd)

    async def send_placeholder(self, chat_id: str, text: str, *, thread_id: str | None = None) -> str | None:
        """Send a placeholder message and return its key (JSON) for later editing."""
        if not self._process or not self._connected.is_set():
            return None

        jid = _normalize_jid(chat_id)
        nonce = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, object]] = loop.create_future()
        self._sent_futures[nonce] = fut

        self._write_cmd({"type": "send", "to": jid, "text": f"[Myrm AI] {text}", "nonce": nonce})

        try:
            key = await asyncio.wait_for(fut, timeout=10.0)
            return json.dumps(key)
        except TimeoutError:
            self._sent_futures.pop(nonce, None)
            logger.warning("WhatsAppChannel: send_placeholder timed out for %s", jid)
            return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        """Edit a previously sent WhatsApp message.

        message_id must be a JSON-serialized Baileys message key from send_placeholder.
        """
        if not self._process or not self._connected.is_set():
            return
        key = parse_message_key(message_id)
        if key:
            self._write_cmd({"type": "edit", "to": _normalize_jid(chat_id), "key": key, "text": f"[Myrm AI] {text}"})
            await self._drain()

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        """Delete a previously sent WhatsApp message ("delete for everyone").

        message_id must be a JSON-serialized Baileys message key from send_placeholder.
        """
        if not self._process or not self._connected.is_set():
            return
        key = parse_message_key(message_id)
        if key:
            logger.warning("WhatsAppChannel: delete_message key=%s", message_id[:80])
            self._write_cmd({"type": "delete", "to": _normalize_jid(chat_id), "key": key})
            await self._drain()
        else:
            logger.warning("WhatsAppChannel: delete_message skipped (invalid key)")

    # ------------------------------------------------------------------
    # Bridge event dispatch
    # ------------------------------------------------------------------

    async def _handle_bridge_event(self, raw: str) -> None:
        """Parse and handle a single JSON Line event from the bridge."""
        if not raw:
            return
        try:
            event: dict[str, object] = json.loads(raw)
        except json.JSONDecodeError:
            return

        event_type = event.get("type", "")
        if event_type not in ("qr", "connection", "ready", "message", "reaction"):
            logger.debug("WhatsAppChannel: bridge event: %s", event_type)

        if event_type == "qr":
            qr_data = event.get("data")
            self._qr_code = str(qr_data) if isinstance(qr_data, str) else None
            self._set_connected(False)
            self.emit("qr_code", {"qr": self._qr_code})
            logger.warning("WhatsAppChannel: QR code generated — scan to pair")

        elif event_type == "connection":
            self._handle_connection_event(event)

        elif event_type == "message":
            await self._handle_inbound(event)

        elif event_type == "reaction":
            await self._handle_inbound_reaction(event)

        elif event_type == "groups":
            self._handle_groups_event(event)

        elif event_type == "sent":
            nonce = str(event.get("nonce", ""))
            key = event.get("key")
            fut = self._sent_futures.pop(nonce, None)
            if fut and not fut.done() and isinstance(key, dict):
                fut.set_result(key)

        elif event_type == "edit_ok":
            logger.debug("WhatsAppChannel: edit succeeded: key=%s", event.get("key"))

        elif event_type == "media_downloaded":
            msg_id = str(event.get("messageId", ""))
            path = str(event.get("path", ""))
            fut_dl = self._media_download_futures.pop(msg_id, None)
            if fut_dl and not fut_dl.done() and path:
                fut_dl.set_result(path)
            logger.debug("WhatsAppChannel: media downloaded: %s (%s bytes)", msg_id, event.get("size"))

        elif event_type == "lid_resolved":
            lid = str(event.get("lid", ""))
            pn = str(event.get("pn", ""))
            if lid and pn:
                self._lid_to_pn[lid] = pn
                stripped = _strip_device_suffix(lid)
                if stripped != lid:
                    self._lid_to_pn[stripped] = pn
                logger.debug("WhatsAppChannel: LID mapped %s → %s", lid, pn)

        elif event_type == "error":
            logger.warning("WhatsAppChannel: bridge error: %s", event.get("message"))

    def _handle_connection_event(self, event: dict[str, object]) -> None:
        """Handle connection status changes from the bridge."""
        status = event.get("status", "")
        logger.warning("WhatsAppChannel: connection event received: status=%s, event=%s", status, event)
        if status == "open":
            self._qr_code = None
            jid_val = event.get("selfJid")
            self._self_jid = str(jid_val) if isinstance(jid_val, str) else None
            lid_val = event.get("selfLid")
            if isinstance(lid_val, str) and lid_val and self._self_jid:
                pn_jid = f"{self._self_jid.split(':')[0].split('@')[0]}@s.whatsapp.net"
                self._lid_to_pn[lid_val] = pn_jid
                stripped_lid = _strip_device_suffix(lid_val)
                if stripped_lid != lid_val:
                    self._lid_to_pn[stripped_lid] = pn_jid
                logger.info("WhatsAppChannel: self LID mapped %s → %s", lid_val, pn_jid)
            self._set_connected(True)
            self._status = ChannelStatus.RUNNING
            logger.info("WhatsAppChannel: connected (self=%s)", self._self_jid)
            asyncio.get_running_loop().call_later(3.0, self._schedule_post_connect_groups)
        elif status == "logged_out":
            self._qr_code = None
            self._set_connected(False)
            self._status = ChannelStatus.ERROR
            logger.warning("WhatsAppChannel: logged out — re-pair required")
        elif status == "close":
            self._set_connected(False)
            reason = event.get("reason", "unknown")
            logger.warning("WhatsAppChannel: disconnected (%s)", reason)
        elif status == "reconnecting":
            logger.warning("WhatsAppChannel: reconnecting...")

    def _schedule_post_connect_groups(self) -> None:
        """Fetch groups after connection is established (called via call_later)."""
        if self.is_connected:
            asyncio.ensure_future(self._post_connect_groups())

    async def _post_connect_groups(self) -> None:
        """Fetch and broadcast groups after successful connection."""
        try:
            groups = await self.list_groups(force_refresh=True)
            logger.info("WhatsAppChannel: post-connect fetched %d group(s)", len(groups))
        except Exception as exc:
            logger.warning("WhatsAppChannel: post-connect groups fetch failed: %s", exc)

    def _handle_groups_event(self, event: dict[str, object]) -> None:
        """Handle groups list response from the bridge."""
        data = event.get("data", [])
        groups = data if isinstance(data, list) else []

        new_cache = [
            GroupInfo(jid=g.get("jid", ""), name=g.get("name", g.get("jid", "")), channel=self.name)
            for g in groups
            if g.get("jid", "").endswith("@g.us")
        ]
        self._update_groups_cache(new_cache)

        if self._groups_future and not self._groups_future.done():
            self._groups_future.set_result(groups)

    # ------------------------------------------------------------------
    # Inbound message handling
    # ------------------------------------------------------------------

    async def _handle_inbound(self, event: dict[str, object]) -> None:
        """Convert a bridge message event to InboundMessage and emit."""
        import json

        logger.warning("WhatsAppChannel: RAW EVENT = %s", json.dumps(event, indent=2, ensure_ascii=False))

        text = str(event.get("text", "")).strip()
        from_jid = str(event.get("from", ""))
        audio_info = event.get("audio")
        document_info = event.get("document")
        has_content = text or audio_info or document_info

        logger.debug(
            "WhatsAppChannel: received event: text='%s', audio=%s, document=%s, from=%s",
            text,
            bool(audio_info),
            bool(document_info),
            from_jid,
        )

        if not has_content or not from_jid:
            return

        is_group = event.get("isGroup") is True
        from_me = event.get("fromMe") is True

        if is_group:
            raw_sender = str(event.get("participant") or from_jid)
            sender_id = _prefer_pn_jid(
                raw_sender,
                event.get("participantAlt") or self._lid_to_pn.get(raw_sender),
            )
            logger.debug(
                "WhatsAppChannel: checking mention in group %s, self_jid=%s",
                from_jid,
                self._self_jid,
            )
            mentioned = check_mentioned(event, self._self_jid, self._lid_to_pn)
            content_preview = text[:80] if text else ("[document]" if document_info else "[voice]")
            logger.warning(
                "WhatsAppChannel: group inbound from %s (mentioned=%s): %s",
                sender_id,
                mentioned,
                content_preview,
            )
        elif from_me:
            if not is_self_chat(from_jid, self._self_jid, self._lid_to_pn):
                return
            sender_id = _strip_device_suffix(self._self_jid) if self._self_jid else from_jid
            mentioned = False
            content_preview = text[:80] if text else ("[document]" if document_info else "[voice]")
            logger.warning("WhatsAppChannel: self-chat inbound: %s", content_preview)
        else:
            raw_sender = str(event.get("participant") or from_jid)
            sender_id = _prefer_pn_jid(
                raw_sender,
                event.get("fromAlt") or event.get("participantAlt") or self._lid_to_pn.get(raw_sender),
            )
            mentioned = False
            content_preview = text[:80] if text else ("[document]" if document_info else "[voice]")
            logger.warning("WhatsAppChannel: inbound from %s: %s", sender_id, content_preview)

        chat_id = _prefer_pn_jid(from_jid, event.get("fromAlt") or self._lid_to_pn.get(from_jid))

        media_list: list[MediaAttachment] = []
        metadata: dict[str, object] = {
            "message_id": event.get("id"),
            "jid": from_jid,
            "from_self": from_me,
        }
        if "pushName" in event:
            metadata["chat_name"] = event["pushName"]
        if isinstance(audio_info, dict):
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.AUDIO,
                    mime_type=str(audio_info.get("mimetype", "audio/ogg")),
                )
            )
            metadata["voice_message_id"] = audio_info.get("messageId")
            metadata["voice_ptt"] = audio_info.get("ptt", False)
            metadata["voice_seconds"] = audio_info.get("seconds", 0)

        if isinstance(document_info, dict):
            file_name = str(document_info.get("fileName", "document"))
            mime_type = str(document_info.get("mimetype", "application/octet-stream"))
            caption = document_info.get("caption")
            if caption and not text:
                text = str(caption).strip()
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    filename=file_name,
                    mime_type=mime_type,
                    caption=str(caption) if caption else None,
                )
            )
            metadata["document_message_id"] = document_info.get("messageId")
            metadata["document_file_length"] = document_info.get("fileLength", 0)

        media: tuple[MediaAttachment, ...] = tuple(media_list)

        wa_msg_id = event.get("id")
        push_name = event.get("pushName")

        timestamp = event.get("timestamp")
        sent_at = float(timestamp) if timestamp is not None else __import__("time").time()

        reply_to = None
        quoted_msg = event.get("quotedMessage")
        if isinstance(quoted_msg, dict) and quoted_msg.get("content"):
            quoted_sender_id = str(quoted_msg.get("sender_id", ""))
            if quoted_sender_id:
                quoted_sender_id = _prefer_pn_jid(quoted_sender_id, self._lid_to_pn.get(quoted_sender_id))
            reply_to = ReplyContext(
                message_id=str(quoted_msg.get("message_id", "")),
                content=str(quoted_msg.get("content", "")),
                sender_id=quoted_sender_id,
                sender_name=quoted_msg.get("sender_name"),
            )

        inbound = InboundMessage(
            channel="whatsapp",
            sender_id=sender_id,
            content=text,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=chat_id,
            sender_name=str(push_name) if push_name else None,
            is_group=is_group,
            mentioned=mentioned,
            media=media,
            metadata=metadata,
            message_id=str(wa_msg_id) if wa_msg_id else None,
            reply_to=reply_to,
        )
        await self._emit_inbound(inbound)

    async def _handle_inbound_reaction(self, event: dict[str, object]) -> None:
        """Convert a bridge reaction event to InboundMessage and emit.

        Bridge sends: {type: "reaction", emoji: "👍", from: "...", messageId: "..."}
        """
        emoji = str(event.get("emoji", "")).strip()
        if not emoji:
            return

        from_jid = str(event.get("from", ""))
        target_msg_id = str(event.get("messageId", ""))
        sender = _prefer_pn_jid(from_jid, event.get("fromAlt") or self._lid_to_pn.get(from_jid))

        inbound = self._build_inbound(
            sender_id=sender,
            content=emoji,
            chat_id=sender,
            is_group=False,
            mentioned=True,
            message_id=target_msg_id,
            metadata={"reaction": True, "target_message_id": target_msg_id},
        )
        await self._emit_inbound(inbound)

    # ------------------------------------------------------------------
    # Media / voice / groups / typing / reactions
    # ------------------------------------------------------------------

    async def download_voice_message(self, message_id: str) -> Path | None:
        """Request the bridge to download a voice message and return the local path.

        The bridge caches raw Baileys messages for audio; this sends a
        download_media command and waits for the media_downloaded response.
        """
        return await self.download_media(message_id)

    async def download_media(self, message_id: str, timeout: float = 30.0) -> Path | None:
        """Request the bridge to download any media (voice, document, image, video) and return the local path.

        The bridge caches raw Baileys messages; this sends a download_media command
        and waits for the media_downloaded response.
        """
        if not self._process or not self._connected.is_set():
            return None

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        self._media_download_futures[message_id] = fut

        self._write_cmd({"type": "download_media", "messageId": message_id})

        try:
            path_str = await asyncio.wait_for(fut, timeout=timeout)
            return Path(path_str)
        except TimeoutError:
            logger.warning("WhatsAppChannel: download_media timed out: %s", message_id)
            return None
        finally:
            self._media_download_futures.pop(message_id, None)

    async def list_groups(self, force_refresh: bool = False) -> list[GroupInfo]:
        """Return cached groups list or fetch from bridge."""
        if self._is_groups_cache_valid(force_refresh):
            return self._groups_cache.copy()

        if not self._process or not self._connected.is_set():
            return []

        loop = asyncio.get_running_loop()
        self._groups_future = loop.create_future()
        self._write_cmd({"type": "list_groups"})

        try:
            raw_groups = await asyncio.wait_for(self._groups_future, timeout=15.0)
        except TimeoutError:
            logger.info("WhatsAppChannel: list_groups timed out")
            return []
        finally:
            self._groups_future = None

        fresh_groups = [
            GroupInfo(jid=g.get("jid", ""), name=g.get("name", g.get("jid", "")), channel=self.name)
            for g in raw_groups
            if g.get("jid", "").endswith("@g.us")
        ]
        self._update_groups_cache(fresh_groups)
        return fresh_groups

    async def start_typing(self, chat_id: str) -> None:
        """Send composing presence to a WhatsApp chat."""
        if self._process and self._connected.is_set():
            self._write_cmd({"type": "typing", "to": chat_id, "status": "composing"})

    async def stop_typing(self, chat_id: str) -> None:
        """Send paused presence to a WhatsApp chat."""
        if self._process and self._connected.is_set():
            self._write_cmd({"type": "typing", "to": chat_id, "status": "paused"})

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        """Add or remove a reaction emoji on a WhatsApp message."""
        if self._process and self._connected.is_set():
            self._write_cmd({"type": "react", "to": chat_id, "messageId": message_id, "emoji": emoji})

    def resolve_lids_for_pns(self, pns: list[str]) -> None:
        """Send known PN JIDs to the bridge for LID pre-resolution."""
        if self._process and self._connected.is_set() and pns:
            self._write_cmd({"type": "resolve_pns", "pns": pns})

    # ------------------------------------------------------------------
    # Async Login Protocol (SSE Stream)
    # ------------------------------------------------------------------

    async def start_login(
        self,
        method: object,
        *,
        timeout: float = 300.0,
        callback_url: str | None = None,
    ):
        """Start async login flow for WhatsApp Web (QR Code).

        Yields LoginEvent objects for SSE streaming to the frontend.
        """
        if method != LoginMethod.QR_CODE:
            raise ValueError("WhatsAppChannel only supports QR_CODE login method")

        queue: asyncio.Queue[LoginEvent] = asyncio.Queue()

        def _on_qr(data: dict[str, object]) -> None:
            qr_str = str(data.get("qr", ""))
            if qr_str:
                queue.put_nowait(
                    LoginEvent(
                        status=LoginStatus.PENDING,
                        state=LoginState(
                            method=LoginMethod.QR_CODE,
                            qr_code=qr_str,
                            message="Scan the QR code with WhatsApp",
                        ),
                    )
                )

        def _on_conn(data: dict[str, object]) -> None:
            connected = bool(data.get("connected", False))
            if connected:
                queue.put_nowait(
                    LoginEvent(
                        status=LoginStatus.SUCCESS,
                        state=LoginState(
                            method=LoginMethod.QR_CODE,
                            message="Successfully connected to WhatsApp Web",
                        ),
                    )
                )
            else:
                # Disconnect or error
                if self._status == ChannelStatus.ERROR:
                    queue.put_nowait(
                        LoginEvent(
                            status=LoginStatus.FAILED,
                            state=LoginState(
                                method=LoginMethod.QR_CODE,
                                error="Connection failed or logged out",
                            ),
                        )
                    )

        # Register listeners
        self.on("qr_code", _on_qr)
        self.on("connection_change", _on_conn)

        try:
            # If already connected, yield success immediately
            if self.is_connected:
                yield LoginEvent(
                    status=LoginStatus.SUCCESS,
                    state=LoginState(
                        method=LoginMethod.QR_CODE,
                        message="Already connected",
                    ),
                )
                return

            # If we already have a QR code, yield it immediately
            if self._qr_code:
                yield LoginEvent(
                    status=LoginStatus.PENDING,
                    state=LoginState(
                        method=LoginMethod.QR_CODE,
                        qr_code=self._qr_code,
                        message="Scan the QR code with WhatsApp",
                    ),
                )

            # Wait for events
            start_time = asyncio.get_running_loop().time()
            while True:
                elapsed = asyncio.get_running_loop().time() - start_time
                if elapsed > timeout:
                    yield LoginEvent(
                        status=LoginStatus.TIMEOUT,
                        state=LoginState(
                            method=LoginMethod.QR_CODE,
                            error="Login timed out",
                        ),
                    )
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event
                    if event.status in (LoginStatus.SUCCESS, LoginStatus.FAILED, LoginStatus.TIMEOUT):
                        break
                except TimeoutError:
                    continue
        finally:
            # Cleanup listeners
            self.remove_listener("qr_code", _on_qr)
            self.remove_listener("connection_change", _on_conn)
