"""WhatsApp channel — bidirectional messaging via Baileys Node.js bridge.

Python ↔ Node.js IPC via JSON Lines over stdin/stdout.
DM + group messages, LID→PN resolution, mention/reply-to-bot detection.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class every provider implements)
- channels.providers.whatsapp.inbound::WhatsAppInboundMixin (POS: bridge event dispatch, connection state, group sync, message parsing)
- channels.providers.whatsapp.login::WhatsAppLoginMixin (POS: QR-code login event stream)
- channels.providers.whatsapp.bridge::BridgeProcessMixin (POS: Node.js bridge subprocess and IPC)

[OUTPUT]
- WhatsAppChannel: WhatsApp Web bidirectional communication Channel (Baileys 7.x bridge)

[POS]
WhatsApp integration core: lifecycle, outbound bridge stdin commands and media/group/typing/reaction requests.
Inbound events reach it as bridge->WhatsAppInboundMixin._handle_inbound->_emit_inbound.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from functools import partial
from pathlib import Path

from app.channels.core.allow_policy import OPEN_POLICY
from app.channels.core.attachment_delivery import deliver_attachments
from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelSendError
from app.channels.core.mixins import CachedGroupMixin
from app.channels.core.rate_limit import DEFAULT_RATE_LIMIT
from app.channels.protocols.async_login import LoginMethod
from app.channels.providers.whatsapp.bridge import BridgeProcessMixin
from app.channels.providers.whatsapp.helpers import (
    _MAX_TEXT_LENGTH,
    _default_auth_dir,
    _normalize_jid,
    parse_message_key,
)
from app.channels.providers.whatsapp.inbound import WhatsAppInboundMixin
from app.channels.providers.whatsapp.login import WhatsAppLoginMixin
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    GroupInfo,
    MediaAttachment,
    OutboundMessage,
    RenderStyle,
    StartMode,
)

logger = logging.getLogger(__name__)


class WhatsAppChannel(WhatsAppInboundMixin, WhatsAppLoginMixin, BaseChannel, CachedGroupMixin, BridgeProcessMixin):
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
        typing_keepalive_interval=20.0,
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
        """Send text, then attachments, to a WhatsApp chat via the bridge.

        Returns the platform message key (JSON) of the last text chunk sent, or None if only media was
        sent. The bridge acknowledges text only: an attachment counts as sent once the bridge has it, and
        a bridge-side upload failure shows up in the bridge log instead of here.
        """
        if not self._process or not self._connected.is_set():
            raise ChannelSendError("WhatsApp is not connected", channel=self.name)

        jid = _normalize_jid(msg.recipient_id)
        last_key: str | None = None

        if msg.content:
            chunks = list(render(msg, self.render_style))
            quoted_key = self._parse_quoted_key(msg.reply_to_id) if msg.reply_to_id else None
            for idx, chunk in enumerate(chunks):
                nonce = uuid.uuid4().hex[:12]
                loop = asyncio.get_running_loop()
                fut: asyncio.Future[dict[str, object]] = loop.create_future()
                self._sent_futures[nonce] = fut
                cmd: dict[str, object] = {"type": "send", "to": jid, "text": chunk, "nonce": nonce}
                if quoted_key and idx == 0:
                    cmd["quoted_key"] = quoted_key
                self._write_cmd(cmd)
                try:
                    key = await asyncio.wait_for(fut, timeout=10.0)
                    last_key = json.dumps(key)
                except TimeoutError:
                    self._sent_futures.pop(nonce, None)

        await deliver_attachments(
            self.name,
            msg.media,
            partial(self._send_media, jid),
            text_delivered=bool(msg.content),
        )
        logger.info("WhatsAppChannel: sent to %s (media=%d)", jid, len(msg.media))
        return last_key

    @staticmethod
    def _parse_quoted_key(reply_to_id: str) -> dict[str, object] | None:
        """Parse a reply_to_id into a Baileys message key for quoting.

        reply_to_id can be a JSON-serialized Baileys key (from send_placeholder)
        or a raw message ID string. Returns the key dict if valid, None otherwise.
        """
        if not reply_to_id:
            return None
        try:
            key = json.loads(reply_to_id)
            if isinstance(key, dict) and "id" in key:
                return key
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    async def _send_media(self, jid: str, attachment: MediaAttachment) -> None:
        """Hand one attachment to the bridge; raises ``ChannelSendError`` when it has no file or URL to send."""
        if not (attachment.url or attachment.path):
            raise ChannelSendError(f"WhatsApp has no source for {attachment.display_name}", channel=self.name, retriable=False)
        cmd: dict[str, object] = {
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
