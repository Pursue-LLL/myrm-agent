"""WeChat iLink inbound: long-polling loop and ILinkMessage to InboundMessage conversion.

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class; supplies the host members the mixin calls)
- channels.providers._ilink.client::ILinkClient (POS: iLink Bot protocol HTTP client)
- channels.providers._ilink.media::process_inbound_item (POS: inbound media processing)
- channels.providers._ilink.types::ILinkMessage, MessageType (POS: iLink protocol data types)

[OUTPUT]
- WeChatILinkInboundMixin: _poll_loop / _parse_message used by WeChatILinkChannel

[POS]
Inbound half of WeChatILinkChannel. The host owns credentials, client lifecycle and outbound delivery; the mixin only
polls getupdates with exponential backoff and converts messages into InboundMessage.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.channels.core.base import BaseChannel
from app.channels.core.exceptions import ChannelAuthError
from app.channels.providers._ilink.client import ILinkClient
from app.channels.providers._ilink.media import process_inbound_item
from app.channels.providers._ilink.types import ILinkMessage, MessageType
from app.channels.types import ChannelStatus, InboundMessage, MediaAttachment

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 5
_INITIAL_BACKOFF = 2.0
_MAX_BACKOFF = 30.0


class WeChatILinkInboundMixin(BaseChannel):
    """WeChat iLink inbound long-polling for ``WeChatILinkChannel``.

    Requires the host class to provide the attributes below plus ``health``, ``_status``, ``_set_connected``,
    ``_emit_inbound`` and ``_build_inbound`` from ``BaseChannel``.
    """

    _client: ILinkClient
    _get_updates_buf: str
    _context_tokens: dict[str, str]
    _temp_files: set[Path]

    async def _poll_loop(self) -> None:
        backoff = _INITIAL_BACKOFF

        while self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            try:
                messages, new_buf = await self._client.get_updates(self._get_updates_buf)

                backoff = _INITIAL_BACKOFF
                self.health.record_success()

                if new_buf != self._get_updates_buf:
                    self._get_updates_buf = new_buf

                if messages:
                    logger.info("WeChatILinkChannel: received %d message(s)", len(messages))
                for ilink_msg in messages:
                    try:
                        inbound = await self._parse_message(ilink_msg)
                        if inbound:
                            await self._emit_inbound(inbound)
                    except Exception as exc:
                        logger.warning("WeChatILinkChannel: parse error: %s", exc)

            except asyncio.CancelledError:
                break

            except ChannelAuthError:
                logger.warning("WeChatILinkChannel: session expired, stopping")
                self._status = ChannelStatus.DEGRADED
                self._set_connected(False)
                break

            except Exception as exc:
                self.health.record_failure(str(exc))
                failures = self.health.consecutive_failures
                logger.warning(
                    "WeChatILinkChannel: poll error (%d/%d): %s",
                    failures,
                    _MAX_CONSECUTIVE_FAILURES,
                    exc,
                )

                if failures >= _MAX_CONSECUTIVE_FAILURES:
                    logger.warning("WeChatILinkChannel: %d consecutive failures, backing off %ds", failures, _MAX_BACKOFF)
                    self.health.record_success()
                    await asyncio.sleep(_MAX_BACKOFF)
                    backoff = _INITIAL_BACKOFF
                else:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _parse_message(self, ilink_msg: ILinkMessage) -> InboundMessage | None:
        """Parse ILinkMessage into InboundMessage."""
        if ilink_msg.message_type != MessageType.USER:
            return None

        from_user = ilink_msg.from_user_id
        if not from_user:
            return None

        if ilink_msg.context_token:
            self._context_tokens[from_user] = ilink_msg.context_token

        text_parts: list[str] = []
        media_list: list[MediaAttachment] = []

        for item in ilink_msg.item_list:
            await process_inbound_item(
                item,
                text_parts,
                media_list,
                self._temp_files,
                self._client.base_url,
                self._client.http,
            )

        content = "\n".join(text_parts)
        if not content and not media_list:
            return None

        is_group = bool(ilink_msg.group_id)
        chat_id: str = ilink_msg.group_id if ilink_msg.group_id else from_user

        mentioned = False
        if is_group and content:
            bot_name = self._client.credentials.ilink_bot_id if self._client.credentials else ""
            mentioned = f"@{bot_name}" in content or "@bot" in content.lower()

        metadata: dict[str, object] = {
            "context_token": ilink_msg.context_token,
            "session_id": ilink_msg.session_id,
            "message_id": ilink_msg.message_id,
            "group_id": ilink_msg.group_id,
        }

        return self._build_inbound(
            sender_id=from_user,
            content=content,
            chat_id=chat_id,
            sender_name=ilink_msg.from_user_name,
            is_group=is_group,
            mentioned=mentioned,
            media=tuple(media_list),
            metadata=metadata,
            message_id=str(ilink_msg.message_id) if ilink_msg.message_id else "",
        )
