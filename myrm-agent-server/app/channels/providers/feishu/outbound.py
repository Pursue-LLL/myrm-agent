"""Feishu outbound: message send (text / post / card), media upload, CardKit streaming and reactions.

[INPUT]
- channels.providers.feishu.cards (POS: card / post content builders)
- channels.providers.feishu.reactions::UNICODE_TO_FEISHU_EMOJI (POS: reaction emoji vocabulary)
- channels.rendering.renderer::render (POS: channel message rendering pipeline)
- channels.types::OutboundMessage, MediaAttachment (POS: channel message value types)

[OUTPUT]
- FeishuOutboundMixin: send, placeholder / edit / delete, media upload and CardKit streaming used by FeishuChannel

[POS]
Outbound half of FeishuChannel. The host owns the API client and the render configuration; the mixin only builds and sends messages.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
import uuid
from datetime import UTC, datetime

from app.channels.rendering.renderer import render
from app.channels.types import (
    MediaAttachment,
    MediaType,
    OutboundMessage,
    RenderStyle,
)

from .api import FeishuClient
from .cards import (
    build_card_actions,
    build_post_content,
    build_result_card,
    build_thinking_card,
    has_rich_text,
    wrap_text_as_card,
)
from .reactions import UNICODE_TO_FEISHU_EMOJI

logger = logging.getLogger(__name__)

_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_TABLE_RE = re.compile(
    r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
    re.MULTILINE,
)


class FeishuOutboundMixin:
    """Feishu outbound message delivery for ``FeishuChannel``.

    Requires the host class to provide the attributes below.
    """

    render_style: RenderStyle
    _client: FeishuClient
    _render_mode: str
    _reaction_ids: dict[str, str]
    _streaming_card_ids: dict[str, str]
    _streaming_seq: dict[str, int]

    async def send(self, msg: OutboundMessage) -> str | None:
        chat_id = msg.recipient_id
        if not chat_id:
            logger.warning("FeishuChannel: no recipient_id, skipping")
            return None

        from .comment_handler import COMMENT_DOC_PREFIX

        if chat_id.startswith(COMMENT_DOC_PREFIX):
            return await self._send_comment_reply(chat_id, msg)

        receive_type = self._resolve_receive_type(chat_id, msg)
        last_msg_id: str | None = None

        for attachment in msg.media:
            mid = await self._send_media(chat_id, receive_type, attachment, msg.reply_to_id)
            if mid:
                last_msg_id = mid

        if msg.content:
            from .table_slicer import slice_card_markdown

            # In raw mode or rich post mode, use standard render chunking
            if self._render_mode == "raw" or (self._render_mode != "card" and not self._should_use_card(msg.content, msg)):
                content_chunks = render(msg, self.render_style)
            else:
                # In card mode, apply table slicing and Lark Markdown protection across 24KB boundaries
                content_chunks = slice_card_markdown(msg.content)

            for i, chunk in enumerate(content_chunks):
                is_last = i == len(content_chunks) - 1
                chunk_msg = dataclasses.replace(
                    msg,
                    content=chunk,
                    quick_replies=msg.quick_replies if is_last else (),
                    components=msg.components if is_last else (),
                    metadata=msg.metadata if is_last else None,
                )
                msg_type, content = self._format_outbound(chunk_msg)
                mid_str = await self._client.send_message(
                    chat_id,
                    msg_type,
                    content,
                    receive_id_type=receive_type,
                    reply_in_thread=bool(msg.reply_to_id),
                )
                if mid_str:
                    last_msg_id = mid_str

        return last_msg_id

    async def _send_comment_reply(self, recipient_id: str, msg: OutboundMessage) -> str | None:
        """Route outbound message to Feishu document comment API."""
        from .comment_handler import (
            _NO_REPLY_SENTINEL,
            deliver_comment_reply,
            parse_comment_recipient,
        )

        route = parse_comment_recipient(recipient_id)
        if not route:
            logger.warning("FeishuChannel: malformed comment recipient_id: %s", recipient_id)
            return None

        content = (msg.content or "").strip()
        if not content or _NO_REPLY_SENTINEL in content:
            logger.info("FeishuChannel: comment NO_REPLY, skipping delivery")
            return None

        ok = await deliver_comment_reply(self._client, route, content)
        if ok:
            logger.info("FeishuChannel: comment reply delivered to %s", recipient_id)
        else:
            logger.error("FeishuChannel: comment reply delivery failed for %s", recipient_id)
        return recipient_id if ok else None

    async def send_placeholder(
        self,
        chat_id: str,
        text: str,
        *,
        thread_id: str | None = None,
    ) -> str | None:
        receive_type = self._resolve_receive_type(chat_id)
        card_id = str(uuid.uuid4())
        card = build_thinking_card(text, card_id=card_id)
        content = json.dumps(card, ensure_ascii=False)
        msg_id = await self._client.send_message(
            chat_id,
            "interactive",
            content,
            receive_id_type=receive_type,
        )
        if msg_id:
            ok = await self._client.streaming_card_create(card_id)
            if ok:
                self._streaming_card_ids[msg_id] = card_id
                self._streaming_seq[msg_id] = 1
            else:
                logger.debug("CardKit streaming init failed, will use edit fallback")
        return msg_id

    async def edit_message(self, chat_id: str, message_id: str, text: str) -> None:
        if await self._streaming_update(message_id, text):
            return
        card = wrap_text_as_card(text)
        content = json.dumps(card, ensure_ascii=False)
        await self._client.edit_message(message_id, "interactive", content)

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        """Replace placeholder with a rich result card; finalize streaming if active."""
        await self._streaming_finalize(message_id, msg.content or "")
        card = self._build_outbound_card(msg)
        content = json.dumps(card, ensure_ascii=False)
        await self._client.edit_message(message_id, "interactive", content)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        await self._client.delete_message(message_id)

    @staticmethod
    def _resolve_receive_type(
        chat_id: str,
        msg: OutboundMessage | None = None,
    ) -> str:
        if msg and msg.metadata:
            explicit = msg.metadata.get("receive_type")
            if explicit:
                return str(explicit)
        return "chat_id" if chat_id.startswith("oc_") else "open_id"

    def _format_outbound(self, msg: OutboundMessage) -> tuple[str, str]:
        """Three-level format detection: text → post → card."""
        content = msg.content or ""
        if self._render_mode == "raw":
            return "text", json.dumps({"text": content}, ensure_ascii=False)
        if self._render_mode == "card" or self._should_use_card(content, msg):
            return "interactive", json.dumps(self._build_outbound_card(msg), ensure_ascii=False)
        if has_rich_text(content):
            return "post", json.dumps(build_post_content(content), ensure_ascii=False)
        return "text", json.dumps({"text": content}, ensure_ascii=False)

    def _should_use_card(self, content: str, msg: OutboundMessage) -> bool:
        from app.channels.types import extract_cron_context

        return bool(
            extract_cron_context(msg)
            or msg.quick_replies
            or msg.components
            or _CODE_BLOCK_RE.search(content)
            or _TABLE_RE.search(content)
            or self._extract_sources(msg)
            or len(content) > 2000
        )

    def _build_outbound_card(self, msg: OutboundMessage) -> dict[str, object]:
        from app.channels.types import extract_cron_context

        cron = extract_cron_context(msg)
        content = msg.content or ""
        cost_meta = msg.metadata.get("cost_metadata") if msg.metadata else None
        card = build_result_card(
            content,
            title=cron.job_name if cron else "",
            sources=self._extract_sources(msg),
            success=cron.success if cron else None,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            cost_metadata=cost_meta,
        )
        actions = build_card_actions(msg.quick_replies, msg.components)
        if actions:
            elems = card.get("elements")
            if isinstance(elems, list):
                elems.extend(actions)
        return card

    @staticmethod
    def _extract_sources(msg: OutboundMessage) -> list[dict[str, object]]:
        if not msg.metadata:
            return []
        sources = msg.metadata.get("sources")
        if isinstance(sources, list):
            return sources  # type: ignore[return-value]
        return []

    async def _send_media(
        self,
        receive_id: str,
        receive_type: str,
        attachment: MediaAttachment,
        reply_to_id: str | None = None,
    ) -> str | None:
        data = await self._download_attachment(attachment)
        if not data:
            return None

        if attachment.media_type == MediaType.IMAGE:
            image_key = await self._client.upload_image(data)
            if not image_key:
                return None
            content = json.dumps({"image_key": image_key})
            msg_type = "image"
        else:
            fname = attachment.filename or f"file.{attachment.media_type.value}"
            file_key = await self._client.upload_file(data, fname)
            if not file_key:
                return None
            content = json.dumps({"file_key": file_key, "file_name": fname})
            msg_type = "file"

        return await self._client.send_message(
            receive_id,
            msg_type,
            content,
            receive_id_type=receive_type,
            reply_in_thread=bool(reply_to_id),
        )

    async def _download_attachment(self, attachment: MediaAttachment) -> bytes | None:
        from pathlib import Path

        if attachment.path:
            try:
                return Path(attachment.path).read_bytes()
            except OSError as exc:
                logger.debug("Failed to read local file %s: %s", attachment.path, exc)
                return None
        return await self._client.download_url(attachment.url) if attachment.url else None

    async def react_to_message(self, chat_id: str, message_id: str, emoji: str) -> None:
        if not message_id:
            return
        try:
            if not emoji:
                reaction_id = self._reaction_ids.pop(message_id, "")
                if reaction_id:
                    await self._client.delete_reaction(message_id, reaction_id)
                return
            feishu_emoji = UNICODE_TO_FEISHU_EMOJI.get(emoji, emoji)
            rid = await self._client.add_reaction(message_id, feishu_emoji)
            if rid:
                self._reaction_ids[message_id] = rid
        except Exception:
            logger.debug("Feishu reaction failed for %s (emoji=%s)", message_id, emoji)

    async def _streaming_update(self, message_id: str, text: str) -> bool:
        """Push incremental streaming; returns False to fall back to edit."""
        card_id = self._streaming_card_ids.get(message_id)
        if not card_id:
            return False
        seq = self._streaming_seq.get(message_id, 1) + 1
        ok = await self._client.streaming_card_update(card_id, text, seq=seq)
        if ok:
            self._streaming_seq[message_id] = seq
        return ok

    async def _streaming_finalize(self, message_id: str, text: str) -> None:
        """Send the final streaming update and clean up the session."""
        card_id = self._streaming_card_ids.pop(message_id, "")
        seq = self._streaming_seq.pop(message_id, 1)
        if not card_id:
            return
        await self._client.streaming_card_update(
            card_id,
            text,
            seq=seq + 1,
            is_final=True,
        )
