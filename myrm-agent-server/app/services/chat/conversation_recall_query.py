"""Conversation Recall query planning helpers.

[INPUT]
myrm_agent_harness.utils.db.fts5::sanitize_fts5_query (POS: FTS5 query sanitizer)

[OUTPUT]
ConversationRecallFtsQuery: Planned FTS query with score weight.
build_conversation_recall_fts_queries: Build exact-first, no-LLM recall query plan.

[POS]
Conversation Recall 查询规划辅助层。为自然语言历史召回提供本地 OR fallback，避免在业务检索路径调用 LLM。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query

MAX_FALLBACK_TERMS = 8
MIN_LATIN_TERM_LENGTH = 2

_TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "before",
    "did",
    "do",
    "for",
    "how",
    "i",
    "in",
    "is",
    "it",
    "last",
    "me",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "we",
    "what",
    "when",
    "with",
    "you",
    "之前",
    "上次",
    "那个",
    "这个",
    "怎么",
    "什么",
    "为什么",
    "我们",
    "讨论",
    "说过",
}


@dataclass(frozen=True, slots=True)
class ConversationRecallFtsQuery:
    """A planned FTS query and its relative score weight."""

    query: str
    score_weight: float


def build_conversation_recall_fts_queries(raw_query: str, safe_query: str) -> list[ConversationRecallFtsQuery]:
    """Build an exact-first FTS query plan with a local broad-recall fallback."""

    exact = safe_query.strip()
    queries: list[ConversationRecallFtsQuery] = []
    if exact:
        queries.append(ConversationRecallFtsQuery(query=exact, score_weight=1.0))

    fallback = _fallback_or_query(raw_query)
    if fallback and fallback != exact:
        queries.append(ConversationRecallFtsQuery(query=fallback, score_weight=0.9))
    return queries


def _fallback_or_query(raw_query: str) -> str:
    terms = _extract_terms(raw_query)
    if len(terms) < 2:
        return ""
    safe_terms = [safe for term in terms if (safe := sanitize_fts5_query(term))]
    if len(safe_terms) < 2:
        return ""
    return " OR ".join(safe_terms)


def _extract_terms(raw_query: str) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for match in _TOKEN_PATTERN.finditer(raw_query.lower()):
        term = match.group(0).strip("_")
        if not _is_recall_term(term) or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= MAX_FALLBACK_TERMS:
            break
    return terms


def _is_recall_term(term: str) -> bool:
    if not term or term in _STOP_WORDS:
        return False
    if term.isascii() and len(term) < MIN_LATIN_TERM_LENGTH:
        return False
    return True
