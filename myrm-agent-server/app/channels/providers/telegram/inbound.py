"""Telegram inbound message parsing, polling, and media-group aggregation.

Mixin providing all inbound-related methods used by TelegramChannel.
Handles message, edited_message, callback_query, sticker, location, venue, and media groups.

[INPUT]
- channels.types::InboundMessage, MediaAttachment, ReplyContext
- telegram.models::TgUpdate, (POS: Pydantic models for Telegram Bot API webhook payloads.)

[OUTPUT]
- TelegramInboundMixin: mixin class providing _parse_update, _buffer_or_emit, _poll_loop, etc.
- `_message_mentions_bot`: entity-based mention detection (text/caption, mention/text_mention/bot_command).
- `_strip_bot_mention_text`: strip @bot prefix from group trigger content before agent dispatch.

[POS]
Telegram inbound message parsing, polling loop, and media group aggregation mixin.
Supports message/edited_message/callback_query/sticker/location/venue. Sets
`explicit_mention` metadata for guest-mode gating. Webhook payloads validated via Pydantic models.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    ReplyContext,
)

from .helpers import (
    _CONFLICT_RETRY_DELAY,
    _DEGRADED_THRESHOLD,
    _MAX_CONFLICT_RETRIES,
    _POLL_BACKOFF_FACTOR,
    _POLL_BACKOFF_INITIAL,
    _POLL_BACKOFF_MAX,
    POLL_TIMEOUT,
)
from .models import TgCallbackQuery, TgEntity, TgMessage, TgMessageReactionUpdated, TgUpdate

if TYPE_CHECKING:
    from .api import TelegramClient
    from .helpers import _MediaGroupBuffer

logger = logging.getLogger(__name__)

_MEDIA_GROUP_DEBOUNCE = 0.5
_MEDIA_GROUP_DEADLINE = 3.0

_ALLOWED_UPDATES = ["message", "edited_message", "callback_query", "message_reaction"]


class TelegramInboundMixin:
    """Mixin providing Telegram inbound message parsing and media-group aggregation.

    Requires the host class to have:
    - self._client: TelegramClient
    - self._bot_username: str | None
    - self._tg_bot_id: int | None
    - self._mg_buffers: dict[str, _MediaGroupBuffer]
    - self._mg_tasks: dict[str, asyncio.Task[None]]
    - self._emit_inbound(msg): coroutine
    - self._build_inbound(**kwargs): InboundMessage
    - self._redact(text): str
    """

    _client: TelegramClient
    _bot_username: str | None
    _tg_bot_id: int | None
    _mg_buffers: dict[str, _MediaGroupBuffer]
    _mg_tasks: dict[str, asyncio.Task[None]]
    _background_tasks: set[asyncio.Task[None]]
    _status: ChannelStatus
    _offset: int

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

    def _parse_reply_to_message(self, reply_msg: TgMessage) -> ReplyContext | None:
        """Parse a replied-to message into structured ReplyContext.

        Supports: text, caption, photo, document, video, audio/voice, sticker.
        Returns: ReplyContext with message content and media attachments.
        """
        text = reply_msg.text
        caption = reply_msg.caption
        content = ""
        if text and text.strip():
            content = text.strip()
        elif caption and caption.strip():
            content = caption.strip()
        elif reply_msg.sticker and reply_msg.sticker.emoji:
            content = reply_msg.sticker.emoji

        media_list: list[MediaAttachment] = []

        if reply_msg.photo:
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE))

        if reply_msg.document:
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    mime_type=reply_msg.document.mime_type,
                    filename=reply_msg.document.file_name or None,
                )
            )

        if reply_msg.video:
            media_list.append(MediaAttachment(media_type=MediaType.VIDEO))

        voice_data = reply_msg.voice or reply_msg.audio
        if voice_data:
            media_list.append(MediaAttachment(media_type=MediaType.AUDIO, mime_type=voice_data.mime_type))

        if reply_msg.sticker:
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE))

        if not content and not media_list:
            return None

        sender_name = None
        sender_id = None
        if reply_msg.from_user:
            sender_id = str(reply_msg.from_user.id)
            sender_name = (
                " ".join(
                    filter(
                        None,
                        (
                            reply_msg.from_user.first_name,
                            getattr(reply_msg.from_user, "last_name", None),
                        ),
                    )
                )
                or reply_msg.from_user.username
            )

        timestamp = None
        if hasattr(reply_msg, "date") and reply_msg.date:
            try:
                timestamp = float(reply_msg.date)
            except (ValueError, TypeError):
                pass

        return ReplyContext(
            message_id=str(reply_msg.message_id) if reply_msg.message_id else "unknown",
            content=content,
            media=tuple(media_list),
            sender_id=sender_id,
            sender_name=sender_name,
            timestamp=timestamp,
        )

    def _parse_message_model(self, msg: TgMessage, *, is_edit: bool) -> InboundMessage | None:
        """Convert a validated TgMessage into an InboundMessage."""
        from_user = msg.from_user
        if from_user is None:
            return None

        text = msg.text
        caption = msg.caption
        has_text = bool(text and text.strip()) or bool(caption and caption.strip())

        media_list: list[MediaAttachment] = []
        tg_display_name = (
            " ".join(filter(None, (from_user.first_name, getattr(from_user, "last_name", None)))) or from_user.username
        )

        metadata: dict[str, object] = {
            "message_id": msg.message_id,
            "username": from_user.username,
            "chat_type": "",
            "is_edit": is_edit,
        }
        language_code = getattr(from_user, "language_code", None)
        if language_code:
            metadata["language_code"] = str(language_code)

        if msg.photo:
            largest = msg.photo[-1]
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
            metadata["photo_file_id"] = largest.file_id

        if msg.document:
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    mime_type=msg.document.mime_type,
                    filename=msg.document.file_name or None,
                )
            )
            metadata["document_file_id"] = msg.document.file_id

        if msg.video:
            media_list.append(MediaAttachment(media_type=MediaType.VIDEO))
            metadata["video_file_id"] = msg.video.file_id

        voice_data = msg.voice or msg.audio
        if voice_data:
            media_list.append(MediaAttachment(media_type=MediaType.AUDIO, mime_type=voice_data.mime_type))
            metadata["voice_file_id"] = voice_data.file_id
            metadata["voice_duration"] = voice_data.duration
            metadata["voice_is_voice_note"] = msg.voice is not None

        if msg.sticker:
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
            metadata["sticker_file_id"] = msg.sticker.file_id
            metadata["sticker_file_unique_id"] = msg.sticker.file_unique_id
            metadata["sticker_emoji"] = msg.sticker.emoji
            metadata["sticker_set_name"] = msg.sticker.set_name
            metadata["sticker_is_animated"] = msg.sticker.is_animated
            metadata["sticker_is_video"] = msg.sticker.is_video
            metadata["is_sticker"] = True
            if not has_text and msg.sticker.emoji:
                has_text = True

        if not has_text:
            if msg.venue:
                loc = msg.venue.location
                parts = [f'[Venue: "{msg.venue.title}"']
                if msg.venue.address:
                    parts.append(f"Address: {msg.venue.address}")
                map_q = f"{loc.latitude},{loc.longitude}"
                parts.append(map_q)
                parts.append(f"Map: https://www.google.com/maps/search/?api=1&query={map_q}]")
                text = " | ".join(parts)
                has_text = True
            elif msg.location:
                loc = msg.location
                map_q = f"{loc.latitude},{loc.longitude}"
                text = f"[Location: {map_q} | Map: https://www.google.com/maps/search/?api=1&query={map_q}]"
                has_text = True

        if not has_text and not media_list:
            return None

        chat = msg.chat
        chat_id = str(chat.id) if chat else ""
        chat_type = chat.type if chat else ""
        metadata["chat_type"] = chat_type
        if chat and chat.title:
            metadata["chat_name"] = chat.title

        is_group = chat_type in ("group", "supergroup")
        explicit_mention = self._message_mentions_bot(msg) if is_group else False
        mentioned = explicit_mention

        reply_to: ReplyContext | None = None
        reply_to_id: str | None = None
        if msg.reply_to_message:
            reply_to_id = str(msg.reply_to_message.message_id)
            reply_to = self._parse_reply_to_message(msg.reply_to_message)
            if is_group and not mentioned and msg.reply_to_message.from_user:
                if msg.reply_to_message.from_user.id == self._tg_bot_id:
                    mentioned = True

        if explicit_mention:
            metadata[METADATA_EXPLICIT_MENTION_KEY] = "1"

        thread_id = str(msg.message_thread_id) if msg.message_thread_id is not None else None

        if chat and chat.is_forum is not None:
            metadata["is_forum"] = chat.is_forum

        content = ""
        if text and text.strip():
            content = text.strip()
        elif caption and caption.strip():
            content = caption.strip()
        elif metadata.get("sticker_emoji"):
            content = str(metadata["sticker_emoji"])

        if content and is_group and self._bot_username and (explicit_mention or mentioned):
            content = self._strip_bot_mention_text(content)

        sent_at = float(msg.date) if hasattr(msg, "date") and msg.date is not None else time.time()

        return self._build_inbound(
            sender_id=str(from_user.id),
            content=content,
            sent_at=sent_at,
            sent_timezone="UTC",
            chat_id=chat_id,
            sender_name=tg_display_name or None,
            is_group=is_group,
            is_bot=bool(getattr(from_user, "is_bot", False)),
            mentioned=mentioned,
            media=tuple(media_list),
            reply_to_id=reply_to_id,
            reply_to=reply_to,
            thread_id=thread_id,
            metadata=metadata,
            message_id=str(msg.message_id) if msg.message_id else None,
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
            chat_id=first.chat_id,
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
        if prefix not in ("qr", "act", "sel"):
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
            },
        )

    async def _pre_emit_hook(self, msg: InboundMessage) -> InboundMessage:
        """Hook for subclasses to transform messages before emit. Default: passthrough."""
        return msg

    def _message_mentions_bot(self, msg: TgMessage) -> bool:
        """Return True when Telegram entity metadata explicitly addresses this bot.

        Scans both ``text``/``entities`` and ``caption``/``caption_entities``.
        Supports ``mention``, ``text_mention``, and group ``bot_command`` (/cmd@bot).
        """
        bot_username = (self._bot_username or "").lstrip("@").lower()
        expected = f"@{bot_username}" if bot_username else None

        def _iter_sources() -> list[tuple[str, list[TgEntity]]]:
            sources: list[tuple[str, list[TgEntity]]] = []
            if msg.text:
                sources.append((msg.text, list(msg.entities or [])))
            if msg.caption:
                sources.append((msg.caption, list(msg.caption_entities or [])))
            return sources

        for source_text, entities in _iter_sources():
            for entity in entities:
                entity_type = entity.type
                if entity_type == "mention" and expected:
                    offset = entity.offset
                    length = entity.length
                    if offset < 0 or length <= 0:
                        continue
                    mention_text = source_text[offset : offset + length].strip().lower()
                    if mention_text == expected:
                        return True
                elif entity_type == "text_mention" and entity.user:
                    if entity.user.id == self._tg_bot_id:
                        return True
                elif entity_type == "bot_command" and expected:
                    offset = entity.offset
                    length = entity.length
                    if offset < 0 or length <= 0:
                        continue
                    command_text = source_text[offset : offset + length]
                    at_index = command_text.find("@")
                    if at_index < 0:
                        continue
                    if command_text[at_index:].strip().lower() == expected:
                        return True
        return False

    def _strip_bot_mention_text(self, text: str) -> str:
        """Remove leading @bot mention from group trigger text (Hermes/Slack parity)."""
        if not text or not self._bot_username:
            return text
        username = re.escape(self._bot_username.lstrip("@"))
        cleaned = re.sub(rf"(?i)@{username}\b[,:\-]*\s*", "", text).strip()
        return cleaned or text

    @staticmethod
    def _is_polling_conflict(error: Exception) -> bool:
        """Detect Telegram 409 Conflict (another process polling same token)."""
        text = str(error).lower()
        return (
            "conflict" in type(error).__name__.lower()
            or "terminated by other getupdates request" in text
            or ("409" in text and "conflict" in text)
        )

    async def _poll_loop(self) -> None:
        """Long-polling loop with intelligent error classification.

        Classifies errors into two categories:
        - 409 Conflict: limited retries then mark ERROR (unrecoverable)
        - Network errors: exponential backoff with DEGRADED status feedback
        """
        backoff = _POLL_BACKOFF_INITIAL
        conflict_count = 0
        consecutive_errors = 0

        while self._status in (ChannelStatus.RUNNING, ChannelStatus.DEGRADED):
            try:
                updates = await self._client.get_updates(
                    offset=self._offset,
                    timeout=POLL_TIMEOUT,
                    allowed_updates=_ALLOWED_UPDATES,
                )

                backoff = _POLL_BACKOFF_INITIAL
                if consecutive_errors > 0:
                    consecutive_errors = 0
                    self._status = ChannelStatus.RUNNING
                    self.health.record_success()
                    self._set_connected(True)
                    logger.info("TelegramChannel: polling recovered")

                conflict_count = 0

                for raw_update in updates:
                    try:
                        tg = TgUpdate.model_validate(raw_update)
                    except ValidationError:
                        logger.debug("TelegramChannel: skipping invalid poll update")
                        continue

                    if tg.update_id:
                        self._offset = max(self._offset, tg.update_id + 1)

                    msg = self._parse_update(raw_update)
                    if msg:
                        msg = await self._pre_emit_hook(msg)
                        await self._buffer_or_emit(msg, raw_update)

            except asyncio.CancelledError:
                break
            except Exception as e:
                error_desc = self._redact(str(e))

                if self._is_polling_conflict(e):
                    conflict_count += 1
                    if conflict_count <= _MAX_CONFLICT_RETRIES:
                        logger.warning(
                            "TelegramChannel: polling conflict (%d/%d), "
                            "another process may be polling this token. "
                            "Retrying in %ds...",
                            conflict_count,
                            _MAX_CONFLICT_RETRIES,
                            int(_CONFLICT_RETRY_DELAY),
                        )
                        await asyncio.sleep(_CONFLICT_RETRY_DELAY)
                    else:
                        logger.error(
                            "TelegramChannel: polling conflict persists after %d "
                            "retries. Another process is actively polling this bot "
                            "token. Stopping polling.",
                            _MAX_CONFLICT_RETRIES,
                        )
                        self._status = ChannelStatus.ERROR
                        self.health.record_failure(
                            "Polling conflict: another process is polling this bot token. Stop the other process and restart."
                        )
                        self._set_connected(False)
                        break
                else:
                    consecutive_errors += 1
                    logger.warning(
                        "TelegramChannel: poll error (%d): %s",
                        consecutive_errors,
                        error_desc,
                    )
                    if consecutive_errors >= _DEGRADED_THRESHOLD:
                        self._status = ChannelStatus.DEGRADED
                        self.health.record_failure(error_desc)
                    await asyncio.sleep(min(backoff, _POLL_BACKOFF_MAX))
                    backoff = min(backoff * _POLL_BACKOFF_FACTOR, _POLL_BACKOFF_MAX)
