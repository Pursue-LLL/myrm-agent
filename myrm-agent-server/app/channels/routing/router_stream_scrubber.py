"""Stream content and progress scrubbing utilities for IM channels.

Provides high-signal Stage rolling descriptions and strips raw thinking tags / JSON payloads.

[INPUT]
- re

[OUTPUT]
- scrub_thinking_content: Filter raw <think>...</think> tags and format thinking stage
- normalize_progress_stage: Map raw progress labels / tool executions into human-friendly stage narratives

[POS]
Pure functions for channel progress cleaning, 100% unit testable.
"""

from __future__ import annotations

import re

_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*?$", re.IGNORECASE)
_TOOL_JSON_RE = re.compile(r"\{[\s\S]*?\}")


def scrub_thinking_content(text: str) -> tuple[str, bool]:
    """Scrub <think> tags from streaming text.

    Returns:
        tuple of (cleaned_text, is_thinking)
    """
    if not text:
        return "", False

    lower_text = text.lower()
    # Check if currently inside open <think> tag
    if "<think>" in lower_text and "</think>" not in lower_text:
        cleaned = _THINK_OPEN_RE.sub("", text).strip()
        return cleaned, True

    cleaned = _THINK_TAG_RE.sub("", text).strip()
    return cleaned, False


def normalize_progress_stage(raw_label: str) -> str:
    """Normalize raw tool names / progress labels into user-friendly Stage descriptions.

    Removes raw JSON arguments, redundant technical symbols, and produces high-signal stage labels.
    """
    if not raw_label:
        return "⏳ 思考中..."

    label = raw_label.strip()

    # Strip raw JSON arguments if present
    if "{" in label and "}" in label:
        label = _TOOL_JSON_RE.sub("", label).strip()

    # Normalize common keywords
    lower_label = label.lower()
    if any(k in lower_label for k in ["search", "google", "bing", "query", "搜索", "检索"]):
        if not label.startswith("🔍"):
            return f"🔍 {label}"
    elif any(k in lower_label for k in ["fetch", "browse", "url", "http", "访问", "网页"]):
        if not label.startswith("🌐"):
            return f"🌐 {label}"
    elif any(k in lower_label for k in ["bash", "terminal", "exec", "shell", "代码", "执行"]):
        if not label.startswith("⚡"):
            return f"⚡ {label}"
    elif any(k in lower_label for k in ["file", "read", "write", "doc", "文件", "写入"]):
        if not label.startswith("📂"):
            return f"📂 {label}"
    elif any(k in lower_label for k in ["think", "plan", "reason", "思考", "规划"]):
        if not label.startswith("💭"):
            return f"💭 {label}"
    elif not any(label.startswith(p) for p in ["⏳", "🔍", "🌐", "⚡", "📂", "💭", "✍️", "📊"]):
        return f"⏳ {label}"

    return label
