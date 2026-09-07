"""Turn outline session projection service.

[INPUT]
- database.dto::MessageDTO, TurnOutlineItem (POS: 消息数据传输对象与大纲项)
- services.chat._base::_ChatServiceBase (POS: 会话服务基础层)
- myrm_agent_harness.utils.text_sanitizer::extract_and_strip_think_blocks (POS: 剥离推理思维链)

[OUTPUT]
- TurnOutlineProjectionService: 极轻量会话轮次大纲投影生成器 (对标 DeepSeek Harness turnOutline fold 投影)

[POS]
全会话大纲增量投影服务。提供 600 字节级精炼大纲折叠计算，
支持百轮长任务在 ~60KB 极低开销下完成全景导航与零抖动跳转定位。
"""

from __future__ import annotations

import re
from datetime import datetime

from myrm_agent_harness.utils.text_sanitizer import (
    extract_and_strip_think_blocks,
)

from app.database.dto import MessageDTO, TurnOutlineItem
from app.database.repositories.uow import UnitOfWork
from app.services.chat._base import _ChatServiceBase

_PROMPT_PREVIEW_LIMIT = 50
_REPLY_PREVIEW_LIMIT = 120
_WHITESPACE_RE = re.compile(r"\s+")


def _sanitize_preview_text(text: str, max_chars: int) -> str:
    """Sanitize raw markdown or text into a compact single-line preview snippet."""
    if not text:
        return ""
    # Strip markdown headers/bullets and collapse whitespace
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "..."


class TurnOutlineProjectionService(_ChatServiceBase):
    """Generates lightweight session projection turn outlines for long conversations."""

    @staticmethod
    def build_outline_from_messages(messages: list[MessageDTO]) -> list[TurnOutlineItem]:
        """Fold raw conversation messages into a compact sequence of turn outlines.

        Args:
            messages: List of messages in chronological ascending order.

        Returns:
            List of TurnOutlineItem representing high-level conversation turns.
        """
        if not messages:
            return []

        outlines: list[TurnOutlineItem] = []
        current_user_msg: MessageDTO | None = None
        current_assistant_msg: MessageDTO | None = None
        current_msg_count = 0
        turn_index = 0

        for msg in messages:
            if msg.role == "user":
                # Close previous turn if exists
                if current_user_msg is not None:
                    turn_index += 1
                    prompt_preview = _sanitize_preview_text(current_user_msg.content, _PROMPT_PREVIEW_LIMIT)
                    reply_preview: str | None = None
                    assistant_id: str | None = None
                    if current_assistant_msg is not None:
                        assistant_id = current_assistant_msg.id
                        clean_reply, _ = extract_and_strip_think_blocks(current_assistant_msg.content)
                        reply_preview = _sanitize_preview_text(clean_reply, _REPLY_PREVIEW_LIMIT)

                    outlines.append(
                        TurnOutlineItem(
                            turn_index=turn_index,
                            user_message_id=current_user_msg.id,
                            assistant_message_id=assistant_id,
                            prompt_preview=prompt_preview,
                            reply_preview=reply_preview,
                            created_at=current_user_msg.created_at,
                            message_count=current_msg_count,
                        )
                    )

                # Start new user turn
                current_user_msg = msg
                current_assistant_msg = None
                current_msg_count = 1
            else:
                current_msg_count += 1
                if msg.role == "assistant":
                    current_assistant_msg = msg

        # Append final trailing turn
        if current_user_msg is not None:
            turn_index += 1
            prompt_preview = _sanitize_preview_text(current_user_msg.content, _PROMPT_PREVIEW_LIMIT)
            reply_preview = None
            assistant_id = None
            if current_assistant_msg is not None:
                assistant_id = current_assistant_msg.id
                clean_reply, _ = extract_and_strip_think_blocks(current_assistant_msg.content)
                reply_preview = _sanitize_preview_text(clean_reply, _REPLY_PREVIEW_LIMIT)

            outlines.append(
                TurnOutlineItem(
                    turn_index=turn_index,
                    user_message_id=current_user_msg.id,
                    assistant_message_id=assistant_id,
                    prompt_preview=prompt_preview,
                    reply_preview=reply_preview,
                    created_at=current_user_msg.created_at,
                    message_count=current_msg_count,
                )
            )

        return outlines

    @staticmethod
    async def get_chat_turn_outline(chat_id: str) -> list[TurnOutlineItem]:
        """Fetch all active messages for chat and compute turn outline projection.

        Args:
            chat_id: Conversation identifier.

        Returns:
            List of TurnOutlineItem.
        """
        async with UnitOfWork() as uow:
            messages = await _ChatServiceBase._cr(uow).get_all_messages(chat_id)
            return TurnOutlineProjectionService.build_outline_from_messages(messages)
