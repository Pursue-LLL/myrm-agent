"""Chat service helper types and functions.

[INPUT]
myrm_agent_harness.agent.security.message_filtering::MessageFilterPipeline (POS: framework message filtering pipeline)
app.database.dto::MessageDTO (POS: 聊天与消息数据传输对象)

[OUTPUT]
filter_messages: Filter chat messages before model context construction.
_sanitize_snippet: Sanitize highlighted FTS snippets for UI output.
RetryResult, RegenerateResult, UndoResult, ChannelHistoryEntry: Chat service result DTOs.

[POS]
聊天服务辅助层。集中放置消息过滤、snippet 清理和轻量结果类型，避免 ChatService 门面承载通用细节。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

from myrm_agent_harness.agent.security.message_filtering import (
    FilterConfig,
    FilterContext,
    MessageFilterPipeline,
    SystemRoleFilter,
)

from app.config.settings import settings
from app.database.dto import MessageDTO

logger = logging.getLogger(__name__)

ChatHistoryPairs = list[list[str]]

# Initialize message filter pipeline with harness framework capability
_filter_config = FilterConfig(
    enabled=settings.message_filter.enabled,
    whitelist_api_keys=settings.message_filter.whitelist_api_keys(),
    audit_enabled=True,
)
_message_filter_pipeline = MessageFilterPipeline(
    [
        SystemRoleFilter(_filter_config),
    ]
)

ALLOWED_MESSAGE_ROLES = {"user", "assistant"}


def filter_messages(
    messages: list[MessageDTO],
    api_key: str | None = None,
) -> list[MessageDTO]:
    """Filter messages using harness framework filtering pipeline.

    Args:
        messages: List of Message DTO objects
        api_key: Optional API key for whitelist checks

    Returns:
        Filtered list of messages (system messages removed unless whitelisted)
    """
    context = FilterContext(user_id="sandbox", api_key=api_key)
    message_dicts = [{"role": msg.role, "content": msg.content, "_original": msg} for msg in messages]
    filtered_dicts = _message_filter_pipeline.filter_messages(message_dicts, context)
    return [msg_dict["_original"] for msg_dict in filtered_dicts]


class RetryResult(NamedTuple):
    """retry_last_turn 操作结果。"""

    success: bool
    query: str
    deleted_count: int


class UndoResult(NamedTuple):
    """undo_last_turn 操作结果。"""

    success: bool
    deleted_count: int


class RegenerateResult(NamedTuple):
    """regenerate_last_turn operation result."""

    success: bool
    query: str
    sibling_group_id: str


class ChannelHistoryEntry(NamedTuple):
    """Channel 历史消息条目，携带 created_at 用于确定性时间戳注入。"""

    role: str
    content: str
    created_at: datetime


def _sanitize_snippet(raw_snippet: str) -> str:
    """Sanitize FTS5 snippet: preserve only <mark> tags, escape everything else."""
    import html
    import re

    # Remove reasoning-related tags from FTS5 snippet (case-insensitive) to prevent UI pollution
    raw_snippet = re.sub(
        r"</?(?:think|thought|thinking|reasoning|REASONING_SCRATCHPAD)[^>]*>",
        "",
        raw_snippet,
        flags=re.IGNORECASE,
    )

    placeholder = "\x00MARK\x00"
    placeholder_end = "\x00/MARK\x00"
    safe = raw_snippet.replace("<mark>", placeholder).replace("</mark>", placeholder_end)
    safe = html.escape(safe)
    safe = safe.replace(placeholder, "<mark>").replace(placeholder_end, "</mark>")
    safe = re.sub(r"<(?!/?mark>)", "&lt;", safe)
    return safe
