"""Unit tests for conversation recall CJK query planning and two-tier fallback."""

from __future__ import annotations

from app.services.chat.conversation_recall_query import (
    build_conversation_recall_fts_queries,
)


def test_build_conversation_recall_fts_queries_strict_and_relaxed_tiers() -> None:
    raw_query = "沙箱部署环境"
    safe_query = "沙箱部署环境"
    queries = build_conversation_recall_fts_queries(raw_query, safe_query)

    # 包含严格档 (weight=1.0) 和放宽档 (weight=0.9)
    assert len(queries) >= 2
    strict_q = queries[0]
    assert strict_q.score_weight == 1.0
    assert strict_q.is_relaxed is False
    assert "沙箱" in strict_q.tokens
    assert "部署" in strict_q.tokens
    assert "环境" in strict_q.tokens

    relaxed_q = queries[1]
    assert relaxed_q.score_weight == 0.9
    assert relaxed_q.is_relaxed is True
    # 放宽档已过滤二字词，保留单字
    assert "沙" in relaxed_q.tokens
    assert "箱" in relaxed_q.tokens
    assert "部" in relaxed_q.tokens
    assert "署" in relaxed_q.tokens
    assert "沙箱" not in relaxed_q.tokens


def test_build_conversation_recall_fts_queries_pure_ascii() -> None:
    raw_query = "docker compose up"
    safe_query = "docker compose up"
    queries = build_conversation_recall_fts_queries(raw_query, safe_query)

    # 纯英文无二字 CJK，仅有一档严格查询 (weight=1.0)
    assert len(queries) >= 1
    assert queries[0].is_relaxed is False
    assert queries[0].score_weight == 1.0
    assert "docker" in queries[0].tokens


def test_build_conversation_recall_fts_queries_empty() -> None:
    assert build_conversation_recall_fts_queries("", "") == []
    assert build_conversation_recall_fts_queries("   ", "   ") == []
