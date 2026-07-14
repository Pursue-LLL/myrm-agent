"""Workflow escalation detector — rule-based check for DW Engine suggestion.

[INPUT]
- query: str | list[object] (user message text or multimodal content)
- routing_tier: str | None (from model router)
- AgentStreamSession (for session-aware wrapper)

[OUTPUT]
- should_suggest_workflow(): bool — pure detection on query text
- should_suggest_workflow_for_session(): bool — session-aware guard + detection

[POS]
Rule-based escalation detector. Zero LLM calls; used by stream_loop to emit a
non-blocking workflow_suggestion SSE event for decomposable multi-goal queries.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.stream_session.stream_session_types import AgentStreamSession

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

    if text.count("\n") >= 3:
        score += 1

    return score >= 4


def should_suggest_workflow_for_session(session: AgentStreamSession) -> bool:
    """Session-aware guard: checks user settings and skip flag before detection."""
    if not session.extra_context.get("suggest_workflow_mode", True):
        return False

    engine_params = session.request.engine_params or {}
    if engine_params.get("skipWorkflowSuggestion"):
        return False

    return should_suggest_workflow(
        query=session.request.query,
        routing_tier=session.routing_tier,
    )


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
