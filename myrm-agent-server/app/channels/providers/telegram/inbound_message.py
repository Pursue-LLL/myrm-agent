"""Telegram message conversion: a validated ``TgMessage`` into an ``InboundMessage``.

Mixin providing the message parsing used by TelegramChannel. Handles text and caption, photo, document, video,
voice, sticker, contact, venue and location content, the replied-to message, and group mention detection.

[INPUT]
- channels.types::InboundMessage, MediaAttachment, ReplyContext (POS: inbound message model)
- telegram.models::TgMessage, TgEntity (POS: Pydantic models for Telegram Bot API payloads)

[OUTPUT]
- TelegramMessageParserMixin: _parse_message_model, _parse_reply_to_message, _message_mentions_bot, _strip_bot_mention_text
- `_parse_telegram_vcard`: a contact (with optional vCard) as the metadata card dict.

[POS]
Telegram message conversion mixin. Sets `explicit_mention` metadata for guest-mode gating; the update dispatch that
calls it lives in `inbound`.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from app.channels.types import (
    METADATA_EXPLICIT_MENTION_KEY,
    InboundMessage,
    MediaAttachment,
    MediaType,
    ReplyContext,
)

from .models import TgEntity, TgMessage


def _parse_telegram_vcard(contact: object) -> dict[str, str | list[str]]:
    """Parse a Telegram contact object (with optional vCard) into a dict."""
    from app.channels.media.contact_enrichment import _parse_vcard

    vcard_str = getattr(contact, "vcard", None)
    if vcard_str and isinstance(vcard_str, str):
        parsed = _parse_vcard(vcard_str)
        if parsed:
            return parsed

    result: dict[str, str | list[str]] = {}
    first = getattr(contact, "first_name", "") or ""
    last = getattr(contact, "last_name", "") or ""
    name = f"{first} {last}".strip()
    if name:
        result["name"] = name
    phone = getattr(contact, "phone_number", "") or ""
    if phone:
        result["phones"] = [phone]
    return result


class TelegramMessageParserMixin:
    """Mixin converting a validated Telegram message into an InboundMessage.

    Requires the host class to have:
    - self._bot_username: str | None
    - self._tg_bot_id: int | None
    - self._build_inbound(**kwargs): InboundMessage
    """

    _bot_username: str | None
    _tg_bot_id: int | None

    if TYPE_CHECKING:
        # Provided by the host channel (BaseChannel); declared with its signature for the type checker.
        def _build_inbound(self, sender_id: str, content: str, chat_id: str, **kwargs: object) -> InboundMessage: ...

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

        if msg.video_note:
            media_list.append(MediaAttachment(media_type=MediaType.VIDEO))
            metadata["video_file_id"] = msg.video_note.file_id
            metadata["video_is_video_note"] = True

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
            if msg.contact:
                contact_parts = []
                name_parts = [p for p in [msg.contact.first_name, msg.contact.last_name] if p]
                if name_parts:
                    contact_parts.append(f"Name: {' '.join(name_parts)}")
                if msg.contact.phone_number:
                    contact_parts.append(f"Phone: {msg.contact.phone_number}")
                if msg.contact.vcard:
                    metadata["contact_cards"] = [_parse_telegram_vcard(msg.contact)]
                elif contact_parts:
                    metadata["contact_cards"] = [
                        {
                            "name": " ".join(name_parts),
                            **({"phones": [msg.contact.phone_number]} if msg.contact.phone_number else {}),
                        }
                    ]
                text = "[Shared Contact] " + " | ".join(contact_parts) if contact_parts else "[Shared Contact]"
                has_text = True
            elif msg.venue:
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

        sender_is_bot = bool(getattr(from_user, "is_bot", False))

        reply_to: ReplyContext | None = None
        reply_to_id: str | None = None
        if msg.reply_to_message:
            reply_to_id = str(msg.reply_to_message.message_id)
            reply_to = self._parse_reply_to_message(msg.reply_to_message)
            if is_group and not mentioned and msg.reply_to_message.from_user:
                # Reply-to-bot counts as implicit mention only for human senders:
                # another bot replying to our message must not wake the agent
                # (bot-to-bot loop); bots can still trigger via explicit @mention.
                if msg.reply_to_message.from_user.id == self._tg_bot_id and not sender_is_bot:
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
            is_bot=sender_is_bot,
            mentioned=mentioned,
            media=tuple(media_list),
            reply_to_id=reply_to_id,
            reply_to=reply_to,
            thread_id=thread_id,
            metadata=metadata,
            message_id=str(msg.message_id) if msg.message_id else None,
        )

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
        """Remove leading @bot mention from group trigger text."""
        if not text or not self._bot_username:
            return text
        username = re.escape(self._bot_username.lstrip("@"))
        cleaned = re.sub(rf"(?i)@{username}\b[,:\-]*\s*", "", text).strip()
        return cleaned or text
