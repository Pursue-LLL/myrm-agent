"""WhatsApp inbound: bridge event dispatch, connection state, group sync and message parsing.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies _emit_inbound / _build_inbound / _set_connected)
- channels.providers.whatsapp.helpers (POS: JID normalisation, mention and self-chat detection)
- channels.types::GroupInfo, InboundMessage, MediaAttachment, ReplyContext (POS: channel message value types)

[OUTPUT]
- WhatsAppInboundMixin: _handle_bridge_event dispatcher plus the connection, groups, message and reaction handlers used by WhatsAppChannel

[POS]
Inbound half of WhatsAppChannel. The host owns the bridge process, the pending-request futures and the LID cache; the mixin turns bridge JSON Lines events into channel state changes and InboundMessage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.providers.whatsapp.helpers import (
    _prefer_pn_jid,
    _strip_device_suffix,
    check_mentioned,
    is_self_chat,
)
from app.channels.types import (
    ChannelStatus,
    GroupInfo,
    InboundMessage,
    MediaAttachment,
    MediaType,
    ReplyContext,
)

logger = logging.getLogger(__name__)


class WhatsAppInboundMixin(BaseChannel):
    """Bridge event handling for ``WhatsAppChannel``.

    Requires the host class to provide the attributes below and ``_update_groups_cache``.
    """

    _qr_code: str | None
    _self_jid: str | None
    _groups_future: asyncio.Future[list[dict[str, str]]] | None
    _sent_futures: dict[str, asyncio.Future[dict[str, object]]]
    _media_download_futures: dict[str, asyncio.Future[str]]
    _lid_to_pn: dict[str, str]

    if TYPE_CHECKING:

        def _update_groups_cache(self, groups: list[GroupInfo]) -> None: ...

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

    async def _handle_inbound(self, event: dict[str, object]) -> None:
        """Convert a bridge message event to InboundMessage and emit."""
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
        sent_at = float(timestamp) if timestamp is not None else time.time()

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
