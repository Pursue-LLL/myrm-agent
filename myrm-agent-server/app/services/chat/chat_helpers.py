"""Chat service helper types and functions.

[INPUT]
myrm_agent_harness.agent.security.message_filtering::MessageFilterPipeline (POS: framework message filtering pipeline)
app.database.dto::MessageDTO (POS: 聊天与消息数据传输对象)
app.database.models.chat::WAKEUP_NOTICE_KEY (POS: extra_data marker of the notice rows written for settled background tasks)

[OUTPUT]
filter_messages: Filter chat messages before model context construction.
_sanitize_snippet: Sanitize highlighted FTS snippets for UI output.
RetryResult, RegenerateResult, UndoResult, TruncateResult, ChannelHistoryEntry: Chat service result DTOs.
WAKEUP_MESSAGE_ID_PREFIX: Id prefix of the system-injected user rows that carry async task results back to a chat.
SPILLOVER_EXTRA_KEY: Extra-data key of a user row whose pasted text was parked in a file.
is_wakeup_notice: Whether a row is the system's note about a settled background task, not something a person typed.
shown_user_text: The text a user row is listed by (turn outline, chat lists).
exported_user_text: The text a user row reads as outside the app (export, share page).

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
from app.database.models.chat import WAKEUP_NOTICE_KEY

logger = logging.getLogger(__name__)

ChatHistoryPairs = list[list[str]]

# System wakeups are stored as user rows; this prefix tells them apart from what a person typed.
WAKEUP_MESSAGE_ID_PREFIX = "wakeup_"

# A user row whose pasted text was parked in a file keeps its path, size, hash and opening lines under this key.
SPILLOVER_EXTRA_KEY = "spillover"


def is_wakeup_notice(message: MessageDTO) -> bool:
    """Whether a row is the system's note about a settled background task, which no person typed.

    Such a note belongs to the model's context, not to the conversation a person reads: lists, exports and shared
    pages leave it out.
    """
    return bool((message.extra_data or {}).get(WAKEUP_NOTICE_KEY))


def _parked_paste(message: MessageDTO) -> dict[str, object] | None:
    """The spillover record of a user row whose pasted text was parked in a file, when it has opening lines."""
    spillover = (message.extra_data or {}).get(SPILLOVER_EXTRA_KEY)
    if isinstance(spillover, dict) and isinstance(spillover.get("preview"), str) and spillover["preview"]:
        return spillover
    return None


def shown_user_text(message: MessageDTO) -> str:
    """The text a user row is listed by: the opening lines of a parked paste, else the row's content."""
    parked = _parked_paste(message)
    return str(parked["preview"]) if parked else message.content


def exported_user_text(message: MessageDTO) -> str:
    """The text a user row reads as outside the app: a parked paste is its opening lines and its size.

    The stub the row stores names a file of the owner's workspace, which a reader of an export or of a
    shared page does not have.
    """
    parked = _parked_paste(message)
    if parked is None:
        return message.content
    chars = parked.get("original_char_count")
    size = f" of {chars:,} characters" if isinstance(chars, int) else ""
    return f"{parked['preview']}\u2026\n\n[Pasted text{size}; only its opening is shown.]"


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
    deleted_message_ids: list[str] = []


class UndoResult(NamedTuple):
    """undo_last_turn 操作结果。"""

    success: bool
    deleted_count: int
    deleted_message_ids: list[str] = []


class RegenerateResult(NamedTuple):
    """regenerate_last_turn operation result."""

    success: bool
    query: str
    sibling_group_id: str


class TruncateResult(NamedTuple):
    """truncate_after_message 操作结果。"""

    success: bool
    deleted_count: int


class RewindResult(NamedTuple):
    """rewind_to_message operation result."""

    success: bool
    deleted_count: int
    composer_text: str
    message_index: int
    goal_paused: bool
    error: str | None = None
    reverted_files: list[str] | None = None
    file_warnings: list[str] | None = None
    skipped_files: list[str] | None = None


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
