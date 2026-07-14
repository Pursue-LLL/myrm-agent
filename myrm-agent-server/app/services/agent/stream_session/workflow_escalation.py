"""Workflow escalation detector — rule-based check for DW Engine suggestion.

[INPUT]
- query: str | list[object] (user message text or multimodal content)
- routing_tier: str | None (from model router)

[OUTPUT]
- should_suggest_workflow(): bool — True when query benefits from DW Engine

[POS]
Rule-based escalation detector. Zero LLM calls; used by stream loop to suggest
Dynamic Workflow mode for decomposable multi-goal queries (routing_tier=="reasoning").
"""

from __future__ import annotations

import re

_MULTI_GOAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(\d+)\s*[.、)）]\s*.{4,}", re.MULTILINE),
    re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]", re.MULTILINE),
    re.compile(r"(?:第[一二三四五六七八九十]+|step\s*\d+)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"(?:分别|各自|同时|并行|逐一|一一)", re.MULTILINE),
    re.compile(r"(?:first|second|third|then|next|finally|also|additionally)", re.IGNORECASE),
]

_PARALLEL_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"(\d+)\s*(?:家|个|种|篇|份|组|项|条)", re.MULTILINE),
    re.compile(r"(?:每个|每家|每种|每篇|每份|各个|各家)", re.MULTILINE),
    re.compile(r"(?:compare|对比|比较|调研|分析).{0,20}(?:\d+|多个|几个|各)", re.IGNORECASE),
]

_MIN_QUERY_LENGTH = 30
_MIN_NUMBERED_ITEMS = 3


def should_suggest_workflow(
    query: str | list[object],
    routing_tier: str | None,
) -> bool:
    """Return True if the query is likely to benefit from DW Engine.

    Only triggers for routing_tier=="reasoning" with decomposable structure.
    """
    if routing_tier != "reasoning":
        return False

    text = _extract_text(query)
    if len(text) < _MIN_QUERY_LENGTH:
        return False

    score = 0

    for pattern in _MULTI_GOAL_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            if len(matches) >= _MIN_NUMBERED_ITEMS:
                score += 3
            elif len(matches) >= 2:
                score += 2
            else:
                score += 1

    for pattern in _PARALLEL_KEYWORDS:
        if pattern.search(text):
            score += 2

    newline_count = text.count("\n")
    if newline_count >= 3:
        score += 1

    return score >= 4


def _extract_text(query: str | list[object]) -> str:
    if isinstance(query, str):
        return query
    parts: list[str] = []
    for item in query:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts)


def should_suggest_workflow_for_session(session: object) -> bool:
    """Session-aware wrapper: checks context flags before calling the pure detector.

    Reads `suggest_workflow_mode` from extra_context (set by orchestrator).
    Respects `skipWorkflowSuggestion` engine_param to avoid re-triggering.
    """
    if not getattr(session, "extra_context", {}).get("suggest_workflow_mode", True):
        return False

    request = getattr(session, "request", None)
    if request is None:
        return False

    engine_params = getattr(request, "engine_params", None) or {}
    if engine_params.get("skipWorkflowSuggestion"):
        return False

    return should_suggest_workflow(
        query=getattr(request, "query", ""),
        routing_tier=getattr(session, "routing_tier", None),
    )
