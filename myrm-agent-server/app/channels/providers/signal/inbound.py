"""Signal inbound: WebSocket / polling receive loops and envelope parsing.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies _emit_inbound / _build_inbound)
- channels.providers.signal.api::SignalClient (POS: Signal CLI REST API client)
- channels.providers.signal.helpers (POS: envelope TypedDict structures, constants and mention rendering)
- channels.types::MediaAttachment, guess_media_type (POS: channel message value types)

[OUTPUT]
- SignalInboundMixin: _ws_connect / _poll_once receive loops and the envelope, reaction and data-message parsers used by SignalChannel

[POS]
Inbound half of SignalChannel. The host owns the API client, the account identity and the connection mode; the mixin only turns envelopes into InboundMessage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import cast

from app.channels.core.base import BaseChannel
from app.channels.providers.signal.api import SignalClient
from app.channels.providers.signal.helpers import (
    _POLL_INTERVAL,
    _Attachment,
    _DataMessage,
    _Envelope,
    _Mention,
    _Reaction,
    _ReceivePayload,
    _render_mentions,
)
from app.channels.types import (
    ChannelStatus,
    MediaAttachment,
    guess_media_type,
)

logger = logging.getLogger(__name__)


class SignalInboundMixin(BaseChannel):
    """Signal envelope handling for ``SignalChannel``.

    Requires the host class to provide the attributes below.
    """

    _api: SignalClient
    _api_url: str
    _phone: str
    _account_uuid: str

    async def _ws_connect(self) -> None:
        """Single WebSocket session — runs until connection drops."""
        async for payload in self._api.stream_events():
            if isinstance(payload, dict):
                await self._handle_envelope(cast(_ReceivePayload, payload))

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
