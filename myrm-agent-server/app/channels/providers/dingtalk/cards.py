"""DingTalk AI Card streaming: placeholder card creation, incremental updates and finalization.

[INPUT]
- channels.providers.dingtalk.api::DingTalkApiClient (POS: OpenAPI client with AI Card endpoints)
- channels.types::OutboundMessage (POS: outbound message envelope)

[OUTPUT]
- DingTalkCardMixin: send_placeholder / edit_message / edit_placeholder_message used by DingTalkChannel

[POS]
AI Card half of DingTalkChannel (typewriter-style streaming replies). The host owns the card template id, the API client
and the active-card registry; the mixin only drives the card lifecycle.
"""

from __future__ import annotations

import logging
import uuid

from app.channels.core.exceptions import ChannelSendError
from app.channels.types import OutboundMessage

from .api import DingTalkApiClient
from .helpers import MAX_TEXT_LENGTH

logger = logging.getLogger(__name__)


class DingTalkCardMixin:
    """DingTalk AI Card streaming for ``DingTalkChannel``.

    Requires the host class to provide the attributes below plus ``_normalize_dingtalk_markdown``.
    """

    name: str
    _card_template_id: str
    _api: DingTalkApiClient
    _streaming_cards: dict[str, str]
    _group_conversations: set[str]
    _chat_sender_map: dict[str, str]

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        if not self._card_template_id:
            return None

        await self._finalize_active_cards()

        is_group = chat_id in self._group_conversations
        out_track_id = uuid.uuid4().hex
        if is_group:
            open_space_id = f"dtv1.card//IM_GROUP.{chat_id}"
        else:
            sender_id = self._chat_sender_map.get(chat_id, chat_id)
            open_space_id = f"dtv1.card//IM_ROBOT.{sender_id}"

        ok = await self._api.create_and_deliver_card(
            self._card_template_id,
            out_track_id,
            open_space_id,
            is_group=is_group,
            card_data={"content": text or ""},
        )
        if ok:
            self._streaming_cards[out_track_id] = out_track_id
            return out_track_id
        return None

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if message_id not in self._streaming_cards:
            return
        text = self._normalize_dingtalk_markdown(text)
        await self._api.streaming_update(message_id, "content", text, is_finalize=False)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Finalize the card with the reply; raise when it cannot, so the bus sends the reply as a normal message."""
        track_id = self._streaming_cards.get(message_id)
        if not track_id:
            raise ChannelSendError("DingTalk streaming card is no longer active", channel=self.name, retriable=False)
        content = self._normalize_dingtalk_markdown((msg.content or "")[:MAX_TEXT_LENGTH])
        if not await self._api.streaming_update(track_id, "content", content, is_finalize=True):
            raise ChannelSendError("DingTalk rejected the final card update", channel=self.name)
        del self._streaming_cards[message_id]

    async def _finalize_active_cards(self) -> None:
        """Finalize all active streaming cards to prevent stale 'typing' state."""
        for track_id in list(self._streaming_cards.values()):
            try:
                await self._api.streaming_update(track_id, "content", "", is_finalize=True)
            except Exception:
                logger.debug("Failed to finalize stale card %s", track_id)
        self._streaming_cards.clear()
