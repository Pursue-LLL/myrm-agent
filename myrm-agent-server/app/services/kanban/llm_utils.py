"""Shared LLM utilities for kanban specifier and decomposer.

Extracts common helpers that both ``specifier.py`` and ``decomposer.py``
rely on: JSON extraction, text truncation, CJK detection, and LiteLLM
response usage parsing.

[INPUT]
- core.utils.chat_utils::parse_llm_json_object (POS: 容错 JSON 对象解析 SSOT)

[OUTPUT]
- extract_json_blob: Lenient JSON extraction tolerating fences and prose.
- truncate: Truncate text to a character limit with ellipsis.
- has_cjk: Detect CJK characters for locale-aware prompt selection.
- extract_usage: Pull token counts from a LiteLLM response.

[POS]
Shared LLM helpers for kanban specifier / decomposer.
"""

from __future__ import annotations

from app.core.utils.chat_utils import parse_llm_json_object


def truncate(text: str, limit: int) -> str:
    """Truncate *text* to at most *limit* characters with trailing ellipsis."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "\u2026"


def has_cjk(text: str) -> bool:
    """Detect CJK characters to pick a localized prompt."""
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x30FF:
            return True
    return False


def extract_json_blob(raw: str) -> dict[str, object] | None:
    """Lenient JSON extraction tolerating markdown fences and prose framing.

    Delegates to :func:`app.core.utils.chat_utils.parse_llm_json_object`,
    the shared robust parser that additionally survives unescaped newlines
    inside string literals and multiple objects where the last one is the
    real result (format examples preceding the actual verdict).
    """
    return parse_llm_json_object(raw)


def extract_usage(response: object) -> tuple[int | None, int | None]:
    """Pull (prompt_tokens, completion_tokens) from a LiteLLM response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    prompt_raw = getattr(usage, "prompt_tokens", None)
    completion_raw = getattr(usage, "completion_tokens", None)
    return _coerce_int_or_none(prompt_raw), _coerce_int_or_none(completion_raw)


def _coerce_int_or_none(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return None
