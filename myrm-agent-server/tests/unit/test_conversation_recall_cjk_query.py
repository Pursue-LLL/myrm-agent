"""Unit tests for conversation recall CJK query planning and two-tier fallback."""

from __future__ import annotations

import sqlite3

import pytest
from myrm_agent_harness.utils.db.fts5 import sanitize_fts5_query

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


@pytest.mark.parametrize(
    ("raw_query", "expected"),
    [
        ("a.-b", '"a. b"'),
        ("foo#bar.baz", '"foo bar.baz"'),
        ("v1.2+beta", '"v1.2 beta"'),
    ],
)
def test_a_token_that_holds_several_words_is_searched_as_one_phrase(raw_query: str, expected: str) -> None:
    queries = build_conversation_recall_fts_queries(raw_query, sanitize_fts5_query(raw_query))

    assert queries[0].query == expected


# Raw queries whose ASCII tokens carry punctuation; once sanitized, such a token can hold quoted parts next to a space.
_PUNCTUATED_QUERIES = (
    "a.-b",
    "foo#bar.baz",
    "v1.2+beta",
    "c++ x..y",
    "node.js -a.b",
    "i.e. don't",
    "42 a.-b 日本語",
    "docker compose up",
)


@pytest.mark.parametrize("tokenizer", ["unicode61", "trigram"])
@pytest.mark.parametrize("raw_query", _PUNCTUATED_QUERIES)
def test_every_planned_query_is_one_fts5_can_parse(raw_query: str, tokenizer: str) -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE VIRTUAL TABLE docs USING fts5(content, tokenize='{tokenizer}')")

    planned = build_conversation_recall_fts_queries(raw_query, sanitize_fts5_query(raw_query))

    assert planned
    for fts_query in planned:
        conn.execute("SELECT rowid FROM docs WHERE docs MATCH ?", (fts_query.query,)).fetchall()
