"""Compression intent generation for the business-layer GeneralAgent.

This module derives task focus signals from the current request and recent
human turns, then passes a normalized `compression_intent` payload down to the
framework layer. It intentionally stays in the server layer because the logic
depends on product-facing chat semantics rather than generic agent execution.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

_MAX_FOCUS_FILES = 8
_MAX_FOCUS_MODULES = 8
_MAX_RECENT_HUMAN_TURNS = 4
_MAX_GOAL_HINT_CHARS = 240
_MAX_FAILED_TOOL_CALL_IDS = 12

_FILE_PATTERN = re.compile(
    r"(?<![:/\w.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:"
    r"py|pyi|ts|tsx|js|jsx|mjs|cjs|json|ya?ml|toml|ini|cfg|conf|md|"
    r"sql|go|rs|java|kt|swift|c|cc|cpp|h|hpp|css|scss|html|xml"
    r")(?:\:\d+)?(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_MODULE_PATTERN = re.compile(r"\b[a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){1,7}\b")
_GENERIC_QUERY_HINTS = frozenset(
    {
        "continue",
        "继续",
        "开始实施",
        "继续实施",
        "开始",
        "实施",
        "ok",
        "okay",
    }
)
_MODULE_FILE_SUFFIXES = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
)


def build_compression_intent(
    *,
    query: object,
    chat_history: Sequence[BaseMessage] | None,
) -> dict[str, object] | None:
    """Build a normalized compression intent payload from business-layer inputs."""
    current_query_text = _extract_query_text(query)
    recent_human_texts = _extract_recent_human_texts(chat_history or [])

    analysis_corpus = [current_query_text, *recent_human_texts]
    focus_files = _limit_unique(
        (normalized for text in analysis_corpus for normalized in _extract_file_paths(text)),
        _MAX_FOCUS_FILES,
    )
    focus_modules = _limit_unique(
        (normalized for text in analysis_corpus for normalized in _extract_modules(text)),
        _MAX_FOCUS_MODULES,
    )
    failed_tool_call_ids = _extract_failed_tool_call_ids(chat_history or [])
    user_goal_hint = _build_goal_hint(current_query_text, recent_human_texts)

    if not focus_files and not focus_modules and not failed_tool_call_ids and not user_goal_hint:
        return None

    return {
        "focus_files": focus_files,
        "focus_modules": focus_modules,
        "failed_tool_call_ids": failed_tool_call_ids,
        "user_goal_hint": user_goal_hint,
    }


def _extract_query_text(query: object) -> str:
    if isinstance(query, str):
        return _normalize_whitespace(query)

    if hasattr(query, "resume"):
        resume_val = getattr(query, "resume", "")
        if isinstance(resume_val, str):
            return _normalize_whitespace(resume_val)
        return ""

    if not isinstance(query, list):
        return ""

    text_parts: list[str] = []
    for item in query:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "text":
            text_value = item.get("text")
            if isinstance(text_value, str):
                text_parts.append(text_value)
            continue

        text_value = item.get("text")
        if isinstance(text_value, str):
            text_parts.append(text_value)

    return _normalize_whitespace(" ".join(text_parts))


def _extract_recent_human_texts(chat_history: Sequence[BaseMessage]) -> list[str]:
    texts: list[str] = []
    for message in reversed(chat_history):
        if not isinstance(message, HumanMessage):
            continue
        normalized = _normalize_message_text(message.content)
        if not normalized:
            continue
        texts.append(normalized)
        if len(texts) >= _MAX_RECENT_HUMAN_TURNS:
            break
    texts.reverse()
    return texts


def _normalize_message_text(content: object) -> str:
    if isinstance(content, str):
        return _normalize_whitespace(content)
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
        return _normalize_whitespace(" ".join(parts))
    return ""


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.split()).strip()


def _extract_file_paths(text: str) -> list[str]:
    matches = _FILE_PATTERN.findall(text)
    normalized: list[str] = []
    for match in matches:
        candidate = match.split(":", 1)[0].strip("`'\"")
        if "://" in candidate:
            continue
        candidate = candidate.removeprefix("./")
        if not candidate:
            continue
        normalized.append(candidate)
    return normalized


def _extract_modules(text: str) -> list[str]:
    modules: list[str] = []
    for match in _MODULE_PATTERN.findall(text):
        lowered = match.lower()
        if lowered.startswith(("http.", "https.")):
            continue
        if lowered.endswith(_MODULE_FILE_SUFFIXES):
            continue
        modules.append(match)
    return modules


def _build_goal_hint(current_query_text: str, recent_human_texts: Sequence[str]) -> str:
    candidates = [current_query_text, *reversed(recent_human_texts)]
    for candidate in candidates:
        normalized = _normalize_whitespace(candidate)
        if not normalized:
            continue
        if normalized.lower() in _GENERIC_QUERY_HINTS:
            continue
        return normalized[:_MAX_GOAL_HINT_CHARS]
    return ""


def _extract_failed_tool_call_ids(chat_history: Sequence[BaseMessage]) -> list[str]:
    failed_ids: list[str] = []
    seen: set[str] = set()

    for message in reversed(chat_history):
        if not isinstance(message, ToolMessage):
            continue

        tool_call_id = message.tool_call_id
        if not tool_call_id or tool_call_id in seen:
            continue
        if not _is_failed_tool_message(message):
            continue

        seen.add(tool_call_id)
        failed_ids.append(tool_call_id)
        if len(failed_ids) >= _MAX_FAILED_TOOL_CALL_IDS:
            break

    failed_ids.reverse()
    return failed_ids


def _is_failed_tool_message(message: ToolMessage) -> bool:
    status = getattr(message, "status", None)
    if isinstance(status, str) and status.lower() == "error":
        return True

    content = _normalize_message_text(message.content)
    if not content:
        return False

    content_head = content[:200].lower()
    return (
        content.startswith("[ERROR]")
        or content.startswith("ERROR")
        or " execution failed" in content_head
        or "task failed" in content_head
        or "connection refused" in content_head
        or "timed out" in content_head
        or "traceback" in content_head
    )


def _limit_unique(values: Iterable[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result
