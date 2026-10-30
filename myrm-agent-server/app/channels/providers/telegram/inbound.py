"""Telegram inbound update dispatch and media-group aggregation.

Mixin providing the update-level inbound methods used by TelegramChannel. Handles message and edited_message
dispatch, callback_query and message_reaction conversion, and media groups (debounce plus hard deadline).

[INPUT]
- channels.types::InboundMessage, MediaAttachment (POS: inbound message model)
- telegram.models::TgUpdate, TgCallbackQuery, TgMessageReactionUpdated (POS: Pydantic models for Telegram Bot API payloads)

[OUTPUT]
- TelegramInboundMixin: _parse_update, _parse_reaction_model, _parse_callback_query_model, _buffer_or_emit, _flush_media_group

[POS]
Telegram inbound update dispatch and media-group aggregation mixin. Message conversion lives in `inbound_message`,
the polling loop in `inbound_poll`; _pre_emit_hook is implemented by TelegramHooksMixin on the host channel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.channels.types import InboundMessage, MediaAttachment

from .models import TgCallbackQuery, TgMessageReactionUpdated, TgUpdate

if TYPE_CHECKING:
    from .api import TelegramClient
    from .helpers import _MediaGroupBuffer
    from .models import TgMessage

logger = logging.getLogger(__name__)

_MEDIA_GROUP_DEBOUNCE = 0.5
_MEDIA_GROUP_DEADLINE = 3.0


class TelegramInboundMixin:
    """Mixin providing Telegram update dispatch and media-group aggregation.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._mg_buffers: dict[str, _MediaGroupBuffer]
    - self._mg_tasks: dict[str, asyncio.Task[None]]
    - self._background_tasks: set[asyncio.Task[None]]
    - self._emit_inbound(msg): coroutine
    - self._build_inbound(**kwargs): InboundMessage
    - self._parse_message_model(msg, is_edit=...): InboundMessage | None
    """

    _client: TelegramClient
    _mg_buffers: dict[str, _MediaGroupBuffer]
    _mg_tasks: dict[str, asyncio.Task[None]]
    _background_tasks: set[asyncio.Task[None]]

    if TYPE_CHECKING:
        # Provided by the host channel (BaseChannel, TelegramMessageParserMixin); declared with their signatures
        # for the type checker.
        def _build_inbound(self, sender_id: str, content: str, chat_id: str, **kwargs: object) -> InboundMessage: ...
        async def _emit_inbound(self, msg: InboundMessage) -> None: ...
        def _parse_message_model(self, msg: TgMessage, *, is_edit: bool) -> InboundMessage | None: ...

    def _parse_update(self, update: dict[str, object]) -> InboundMessage | None:
        """Parse a Telegram Update into an InboundMessage using Pydantic validation."""
        try:
            tg = TgUpdate.model_validate(update)
        except ValidationError:
            logger.debug("TelegramChannel: invalid update payload, skipping")
            return None

        if tg.callback_query:
            return self._parse_callback_query_model(tg.callback_query)

        if tg.message_reaction:
            return self._parse_reaction_model(tg.message_reaction)

        is_edit = False
        msg = tg.message
        if msg is None:
            msg = tg.edited_message
            is_edit = True
        if msg is None or msg.from_user is None:
            return None

        return self._parse_message_model(msg, is_edit=is_edit)

    def _parse_reaction_model(self, reaction: TgMessageReactionUpdated) -> InboundMessage | None:
        """Convert a Telegram message_reaction update to InboundMessage."""
        if not reaction.user or not reaction.new_reaction:
            return None

        emoji = ""
        for r in reaction.new_reaction:
            if r.type == "emoji" and r.emoji:
                emoji = r.emoji
                break
        if not emoji:
            return None

        chat_id = str(reaction.chat.id) if reaction.chat else ""
        target_msg_id = str(reaction.message_id) if reaction.message_id else ""
        sender_id = str(reaction.user.id)

        return self._build_inbound(
            sender_id=sender_id,
            content=emoji,
            chat_id=chat_id,
            is_group=bool(reaction.chat and reaction.chat.type in ("group", "supergroup")),
            mentioned=True,
            message_id=target_msg_id,
            metadata={"reaction": True, "target_message_id": target_msg_id},
        )

    async def _buffer_or_emit(self, msg: InboundMessage, update: dict[str, object]) -> None:
        """Route message through media-group buffer or emit directly."""
        try:
            tg = TgUpdate.model_validate(update)
        except ValidationError:
            await self._emit_inbound(msg)
            return

        raw_msg = tg.message or tg.edited_message
        mg_id = raw_msg.media_group_id if raw_msg else None

        if not mg_id:
            await self._emit_inbound(msg)
            return

        from .helpers import _MediaGroupBuffer

        key = f"{msg.chat_id}:{mg_id}"
        if key in self._mg_buffers:
            buf = self._mg_buffers[key]
            buf.messages.append(msg)
            buf.event.set()
        else:
            buf = _MediaGroupBuffer(messages=[msg])
            self._mg_buffers[key] = buf
            self._mg_tasks[key] = asyncio.create_task(self._flush_media_group(key))

    async def _flush_media_group(self, key: str) -> None:
        """Wait for debounce silence or hard deadline, then merge and emit."""
        buf = self._mg_buffers[key]
        try:
            while True:
                elapsed = time.monotonic() - buf.created_at
                remaining = _MEDIA_GROUP_DEADLINE - elapsed
                if remaining <= 0:
                    break
                wait = min(_MEDIA_GROUP_DEBOUNCE, remaining)
                buf.event.clear()
                try:
                    await asyncio.wait_for(buf.event.wait(), timeout=wait)
                except TimeoutError:
                    break
        except asyncio.CancelledError:
            return
        finally:
            self._mg_buffers.pop(key, None)
            self._mg_tasks.pop(key, None)

        if buf.messages:
            merged = self._merge_group(buf.messages)
            await self._emit_inbound(merged)

    def _merge_group(self, messages: list[InboundMessage]) -> InboundMessage:
        """Merge multiple InboundMessages from a media group into one."""
        first = messages[0]
        contents = [m.content for m in messages if m.content]
        all_media: list[MediaAttachment] = []
        for m in messages:
            all_media.extend(m.media)

        merged_metadata = dict(first.metadata) if first.metadata else {}
        merged_metadata["media_group_count"] = len(messages)

        return self._build_inbound(
            sender_id=first.sender_id,
            content="\n".join(contents),
            chat_id=first.chat_id or "",
            sender_name=first.sender_name,
            is_group=first.is_group,
            mentioned=first.mentioned,
            media=tuple(all_media),
            reply_to_id=first.reply_to_id,
            metadata=merged_metadata,
        )

    def _parse_callback_query_model(self, cbq: TgCallbackQuery) -> InboundMessage | None:
        """Convert a validated TgCallbackQuery into an InboundMessage."""
        if cbq.from_user is None:
            return None

        data = cbq.data
        if ":" not in data:
            return None

        prefix, payload = data.split(":", 1)
        if prefix not in ("qr", "act", "sel", "ag"):
            return None

        chat_id = ""
        if cbq.message and cbq.message.chat:
            chat_id = str(cbq.message.chat.id)

        sender_id = str(cbq.from_user.id)
        cbq_display_name = (
            " ".join(
                filter(
                    None,
                    (
                        cbq.from_user.first_name,
                        getattr(cbq.from_user, "last_name", None),
                    ),
                )
            )
            or cbq.from_user.username
        )

        task = asyncio.create_task(self._client.answer_callback_query(cbq.id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        return self._build_inbound(
            sender_id=sender_id,
            content=payload,
            chat_id=chat_id,
            sender_name=cbq_display_name or None,
            is_group=False,
            mentioned=False,
            metadata={
                "callback_query_id": cbq.id,
                "callback_prefix": prefix,
                "username": cbq.from_user.username,
                "origin_message_id": cbq.message.message_id if cbq.message else None,
            },
        )
