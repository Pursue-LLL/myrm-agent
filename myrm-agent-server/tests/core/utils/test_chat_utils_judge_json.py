"""Tests for shared LLM judge JSON parsing helpers in chat_utils.

Covers the tolerant object extraction (markdown fences, prose framing,
unescaped newlines inside string literals) and the done-key judge contract
used by the kanban verifier and the goal semantic judge.
"""

from __future__ import annotations

import pytest

from app.core.utils.chat_utils import parse_judge_json, parse_llm_json_object


# ── parse_llm_json_object ──


class TestParseLlmJsonObject:
    def test_plain_object(self) -> None:
        parsed = parse_llm_json_object('{"score": 0.9, "reasoning": "ok"}')
        assert parsed == {"score": 0.9, "reasoning": "ok"}

    def test_markdown_fence(self) -> None:
        raw = '```json\n{"score": 1.0, "reasoning": "same"}\n```'
        parsed = parse_llm_json_object(raw)
        assert parsed == {"score": 1.0, "reasoning": "same"}

    def test_prose_framing(self) -> None:
        raw = 'Here is my judgement: {"score": 0.7, "reasoning": "close"} End.'
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["score"] == pytest.approx(0.7)

    def test_unescaped_newline_in_string(self) -> None:
        """minimax 等 reasoning 模型在字符串字面量内输出裸换行。"""
        raw = '{"score": 0.95, "reasoning": "line one\nline two"}'
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["reasoning"] == "line one\nline two"

    def test_pretty_printed_preserves_structure(self) -> None:
        raw = '{\n  "score": 0.9,\n  "reasoning": "ok"\n}'
        parsed = parse_llm_json_object(raw)
        assert parsed == {"score": 0.9, "reasoning": "ok"}

    def test_empty_and_garbage_return_none(self) -> None:
        assert parse_llm_json_object("") is None
        assert parse_llm_json_object("   ") is None
        assert parse_llm_json_object("not json at all") is None

    def test_non_dict_json_returns_none(self) -> None:
        assert parse_llm_json_object("[1, 2, 3]") is None


# ── parse_judge_json ──


class TestParseJudgeJson:
    def test_done_key_required(self) -> None:
        assert parse_judge_json('{"status": "ok"}') is None
        assert parse_judge_json("no json") is None

    def test_boolean_normalization(self) -> None:
        for val in ("true", "True", "TRUE", "yes", "Yes", "1"):
            assert parse_judge_json(f'{{"done": "{val}"}}')["done"] is True
        for val in ("false", "False", "no", "No", "0", "nope"):
            assert parse_judge_json(f'{{"done": "{val}"}}')["done"] is False

    def test_unescaped_newline_tolerated(self) -> None:
        raw = '{"done": false, "reason": "still\nworking"}'
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is False
