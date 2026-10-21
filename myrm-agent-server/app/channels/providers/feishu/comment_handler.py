"""Feishu drive document comment handler.

Processes ``drive.notice.comment_add_v1`` events, converts them into
``InboundMessage`` with an encoded ``chat_id`` for routing, and delegates
reply delivery via the channel's ``send`` method.

The encoded chat_id format ``comment-doc:{file_type}:{file_token}:{comment_id}:{is_whole}``
enables zero-intrusion integration with the existing agent pipeline:
1. Comment events -> InboundMessage (encoded chat_id) -> _emit_inbound
2. Agent processes normally, generates OutboundMessage with same recipient_id
3. FeishuChannel.send() detects ``comment-doc:`` prefix -> comment reply API

[INPUT]
- providers.feishu.api::FeishuClient (POS: Feishu OpenAPI client)
- providers.feishu.models::FeishuCommentEvent (POS: comment event model)
- providers.feishu.comment_content (POS: comment content extraction and prompt construction)

[OUTPUT]
- CommentHandler: orchestrates comment event processing
- COMMENT_DOC_PREFIX: routing prefix constant
- parse_comment_recipient: extracts routing info from encoded recipient_id
- deliver_comment_reply: sends text reply via comment API with chunking

[POS]
Feishu drive document comment handler. Converts comment events to InboundMessage
with encoded chat_id for transparent agent pipeline routing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.channels.providers.feishu.comment_content import (
    _extract_docs_links,
    _extract_reply_text,
    _extract_semantic_text,
    _format_referenced_docs,
    _get_reply_user_id,
    _resolve_wiki_links,
    _TimelineEntry,
    build_local_comment_prompt,
    build_whole_comment_prompt,
)

if TYPE_CHECKING:
    from app.channels.providers.feishu.api import FeishuClient

logger = logging.getLogger(__name__)

COMMENT_DOC_PREFIX = "comment-doc:"

_ALLOWED_NOTICE_TYPES = frozenset({"add_comment", "add_reply"})
_REPLY_CHUNK_SIZE = 4000
_NO_REPLY_SENTINEL = "NO_REPLY"


@dataclass(frozen=True, slots=True)
class CommentRouteInfo:
    """Parsed routing info from an encoded comment recipient_id."""

    file_type: str
    file_token: str
    comment_id: str
    is_whole: bool


def encode_comment_chat_id(
    file_type: str,
    file_token: str,
    comment_id: str,
    is_whole: bool,
) -> str:
    """Encode comment routing info into a chat_id string."""
    return f"{COMMENT_DOC_PREFIX}{file_type}:{file_token}:{comment_id}:{1 if is_whole else 0}"


def parse_comment_recipient(recipient_id: str) -> CommentRouteInfo | None:
    """Extract routing info from an encoded comment recipient_id.

    Returns None if the recipient_id is not a comment-doc: encoded string.
    """
    if not recipient_id.startswith(COMMENT_DOC_PREFIX):
        return None
    rest = recipient_id[len(COMMENT_DOC_PREFIX) :]
    parts = rest.split(":", 3)
    if len(parts) != 4:
        logger.warning("Malformed comment recipient_id: %s", recipient_id)
        return None
    return CommentRouteInfo(
        file_type=parts[0],
        file_token=parts[1],
        comment_id=parts[2],
        is_whole=parts[3] == "1",
    )


def chunk_text(text: str, limit: int = _REPLY_CHUNK_SIZE) -> list[str]:
    """Split text into chunks for delivery, preferring line breaks."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


async def deliver_comment_reply(
    client: FeishuClient,
    route: CommentRouteInfo,
    text: str,
) -> bool:
    """Route agent reply to the correct comment API, chunking long text.

    - Whole comment -> add_whole_comment
    - Local comment -> reply_to_comment, fallback to add_whole_comment on 1069302
    """
    chunks = chunk_text(text)
    is_whole = route.is_whole
    all_ok = True

    for chunk in chunks:
        if is_whole:
            ok = await client.add_whole_comment(route.file_token, route.file_type, chunk)
        else:
            success, code = await client.reply_to_comment(
                route.file_token,
                route.file_type,
                route.comment_id,
                chunk,
            )
            if success:
                ok = True
            elif code == 1069302:
                logger.info("Feishu comment reply not allowed (1069302), falling back to add_whole_comment")
                ok = await client.add_whole_comment(route.file_token, route.file_type, chunk)
                is_whole = True
            else:
                ok = False

        if not ok:
            all_ok = False
            break

    return all_ok


# ── Main event handler ─────────────────────────────────────────


class CommentHandler:
    """Orchestrates Feishu document comment event processing.

    Converts a ``drive.notice.comment_add_v1`` event into an ``InboundMessage``
    with encoded ``chat_id`` and submits it to the channel's inbound pipeline.
    """

    def __init__(self, client: FeishuClient, bot_open_id: str) -> None:
        self._client = client
        self._bot_open_id = bot_open_id

    async def handle_comment_event(
        self,
        event_data: dict[str, object],
        channel: object,
    ) -> None:
        """Full orchestration for a drive comment event.

        Args:
            event_data: Raw event dict from webhook payload.
            channel: FeishuChannel instance (provides _build_inbound/_emit_inbound).
        """
        from pydantic import ValidationError

        from app.channels.providers.feishu.models import (
            FeishuCommentEvent,
        )

        try:
            evt = FeishuCommentEvent.model_validate(event_data)
        except ValidationError:
            logger.debug("Feishu comment event validation failed")
            return

        meta = evt.notice_meta
        file_token = meta.file_token
        file_type = meta.file_type
        comment_id = evt.comment_id
        reply_id = evt.reply_id
        from_open_id = meta.from_user_id.open_id
        to_open_id = meta.to_user_id.open_id
        notice_type = meta.notice_type

        if from_open_id and self._bot_open_id and from_open_id == self._bot_open_id:
            logger.debug("Feishu comment: skipping self-authored event")
            return

        if not to_open_id or (self._bot_open_id and to_open_id != self._bot_open_id):
            logger.debug("Feishu comment: skipping event not addressed to self")
            return

        if notice_type and notice_type not in _ALLOWED_NOTICE_TYPES:
            logger.debug("Feishu comment: skipping notice_type=%s", notice_type)
            return

        if not file_token or not file_type or not comment_id:
            logger.warning("Feishu comment: missing required fields, skipping")
            return

        logger.info(
            "Feishu comment: notice=%s file=%s:%s comment=%s from=%s",
            notice_type,
            file_type,
            file_token,
            comment_id,
            from_open_id,
        )

        if reply_id:
            asyncio.ensure_future(
                self._client.add_comment_reaction(
                    file_token,
                    file_type,
                    reply_id,
                    "OK",
                )
            )

        meta_task = asyncio.ensure_future(self._client.query_document_meta(file_token, file_type))
        comment_task = asyncio.ensure_future(self._client.batch_query_comment(file_token, file_type, comment_id))
        doc_meta, comment_detail = await asyncio.gather(meta_task, comment_task)

        doc_title = str(doc_meta.get("title", "Untitled"))
        doc_url = str(doc_meta.get("url", ""))
        is_whole = bool(comment_detail.get("is_whole"))

        if is_whole:
            prompt = await self._build_whole_prompt(
                file_token,
                file_type,
                doc_title,
                doc_url,
                from_open_id,
                comment_detail,
            )
        else:
            prompt = await self._build_local_prompt(
                file_token,
                file_type,
                comment_id,
                reply_id,
                doc_title,
                doc_url,
                from_open_id,
                comment_detail,
            )

        chat_id = encode_comment_chat_id(file_type, file_token, comment_id, is_whole)

        from app.channels.core.base import BaseChannel

        if not isinstance(channel, BaseChannel):
            logger.error("Feishu comment: channel is not a BaseChannel instance")
            return

        inbound = channel._build_inbound(
            sender_id=from_open_id,
            content=prompt,
            sent_at=_time.time(),
            sent_timezone="UTC",
            chat_id=chat_id,
            is_group=False,
            mentioned=True,
            metadata={
                "comment_id": comment_id,
                "file_token": file_token,
                "file_type": file_type,
                "is_whole": is_whole,
                "doc_title": doc_title,
            },
        )
        await channel._emit_inbound(inbound)

        if reply_id:
            await self._client.delete_comment_reaction(
                file_token,
                file_type,
                reply_id,
                "OK",
            )

    async def _build_whole_prompt(
        self,
        file_token: str,
        file_type: str,
        doc_title: str,
        doc_url: str,
        from_open_id: str,
        comment_detail: dict[str, object],
    ) -> str:
        """Build prompt for whole-document comment."""
        whole_comments = await self._client.list_comments(
            file_token,
            file_type,
            is_whole=True,
        )
        timeline: list[_TimelineEntry] = []
        current_text = ""
        current_index = -1
        nearest_self_index = -1

        for wc in whole_comments:
            reply_list = wc.get("reply_list", {})
            if isinstance(reply_list, str):
                try:
                    reply_list = json.loads(reply_list)
                except (json.JSONDecodeError, TypeError):
                    reply_list = {}
            if not isinstance(reply_list, dict):
                continue
            replies = reply_list.get("replies", [])
            if not isinstance(replies, list):
                continue
            for r in replies:
                if not isinstance(r, dict):
                    continue
                uid = _get_reply_user_id(r)
                text = _extract_reply_text(r)
                is_self = uid == self._bot_open_id if self._bot_open_id else False
                idx = len(timeline)
                timeline.append((uid, text, is_self))
                if uid == from_open_id:
                    current_text = _extract_semantic_text(r, self._bot_open_id)
                    current_index = idx
                if is_self:
                    nearest_self_index = idx

        if not current_text:
            for i in range(len(timeline) - 1, -1, -1):
                uid, text, is_self = timeline[i]
                if not is_self:
                    current_text = text
                    current_index = i
                    break

        all_raw_replies = self._collect_raw_replies(whole_comments)
        ref_docs_text = await self._resolve_docs_links(all_raw_replies, file_token)

        return build_whole_comment_prompt(
            doc_title=doc_title,
            doc_url=doc_url,
            file_token=file_token,
            file_type=file_type,
            comment_text=current_text,
            timeline=timeline,
            self_open_id=self._bot_open_id,
            current_index=current_index,
            nearest_self_index=nearest_self_index,
            referenced_docs=ref_docs_text,
        )

    async def _build_local_prompt(
        self,
        file_token: str,
        file_type: str,
        comment_id: str,
        reply_id: str,
        doc_title: str,
        doc_url: str,
        from_open_id: str,
        comment_detail: dict[str, object],
    ) -> str:
        """Build prompt for local (quoted-text) comment."""
        replies = await self._client.list_comment_replies(
            file_token,
            file_type,
            comment_id,
            expect_reply_id=reply_id,
        )

        quote_text = str(comment_detail.get("quote", ""))
        timeline: list[_TimelineEntry] = []
        root_text = ""
        target_text = ""
        target_index = -1

        for i, r in enumerate(replies):
            uid = _get_reply_user_id(r)
            text = _extract_reply_text(r)
            is_self = uid == self._bot_open_id if self._bot_open_id else False
            timeline.append((uid, text, is_self))
            if i == 0:
                root_text = _extract_semantic_text(r, self._bot_open_id)
            rid = str(r.get("reply_id", ""))
            if rid and rid == reply_id:
                target_text = _extract_semantic_text(r, self._bot_open_id)
                target_index = i

        if not target_text:
            for i in range(len(timeline) - 1, -1, -1):
                uid, text, is_self = timeline[i]
                if uid == from_open_id:
                    target_text = text
                    target_index = i
                    break

        ref_docs_text = await self._resolve_docs_links(replies, file_token)

        return build_local_comment_prompt(
            doc_title=doc_title,
            doc_url=doc_url,
            file_token=file_token,
            file_type=file_type,
            comment_id=comment_id,
            quote_text=quote_text,
            root_comment_text=root_text,
            target_reply_text=target_text,
            timeline=timeline,
            self_open_id=self._bot_open_id,
            target_index=target_index,
            referenced_docs=ref_docs_text,
        )

    @staticmethod
    def _collect_raw_replies(
        comments: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Flatten all reply dicts from a list of comments."""
        all_replies: list[dict[str, object]] = []
        for wc in comments:
            rl = wc.get("reply_list", {})
            if isinstance(rl, str):
                try:
                    rl = json.loads(rl)
                except (json.JSONDecodeError, TypeError):
                    rl = {}
            if not isinstance(rl, dict):
                continue
            raw_replies = rl.get("replies", [])
            if isinstance(raw_replies, list):
                all_replies.extend(r for r in raw_replies if isinstance(r, dict))
        return all_replies

    async def _resolve_docs_links(
        self,
        replies: list[dict[str, object]],
        current_file_token: str,
    ) -> str:
        """Extract, resolve wiki links, and format referenced docs."""
        doc_links = _extract_docs_links(replies)
        if doc_links:
            doc_links = await _resolve_wiki_links(self._client, doc_links)
        return _format_referenced_docs(doc_links, current_file_token)
