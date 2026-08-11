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

    def test_multiple_fences_picks_last_parseable_dict(self) -> None:
        """推理模型先给格式示例块、再给真实结果块时应取真实结果（最后者）。"""
        raw = (
            '```json\n{"score": 0.5, "reasoning": "example"}\n```\n'
            '```json\n{"score": 0.95, "reasoning": "real verdict"}\n```'
        )
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["score"] == pytest.approx(0.95)

    def test_oriented_brackets_ignored(self) -> None:
        """孤立 } 与文本中的花括号不破坏对象提取。"""
        raw = 'text } brace {"score": 0.8, "reasoning": "ok"} done'
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["score"] == pytest.approx(0.8)

    def test_fence_then_bare_object_picks_last(self) -> None:
        """fence 块在前、裸对象在后（真实判定）时应取裸对象。"""
        raw = (
            '```json\n{"score": 0.4, "reasoning": "example"}\n```\n'
            'real verdict: {"score": 0.93, "reasoning": "bare object"}'
        )
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["score"] == pytest.approx(0.93)

    def test_object_inside_fence_after_bare_example(self) -> None:
        """裸示例对象在前、fence 真实块在后时应取 fence 真实块。"""
        raw = (
            'example {"score": 0.2, "reasoning": "demo"} then\n'
            '```json\n{"score": 0.99, "reasoning": "fenced verdict"}\n```'
        )
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed["score"] == pytest.approx(0.99)

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

    def test_example_fence_before_real_verdict(self) -> None:
        """示例块在前、真实判定在后的双代码块场景必须取真实判定。"""
        raw = (
            '```json\n{"done": true, "reason": "format example"}\n```\n'
            '```json\n{"done": false, "reason": "real verdict"}\n```'
        )
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is False
        assert parsed["reason"] == "real verdict"

    def test_mini_example_object_in_prose(self) -> None:
        """prose 中先出现迷你示例对象、真实判定在后时应取后者。"""
        raw = 'Example: {"done": true} but real answer is {"done": false, "reason": "nope"}'
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is False

    def test_multiple_done_objects_last_wins(self) -> None:
        """多个含 done 的对象取最后一个（LLM 自我修正/最终判定在末尾）。"""
        raw = (
            '{"done": false, "reason": "first pass"} then '
            '{"done": true, "reason": "after self-correction"}'
        )
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is True

    def test_numeric_done_normalized(self) -> None:
        assert parse_judge_json('{"done": 1}')["done"] is True
        assert parse_judge_json('{"done": 0}')["done"] is False
        assert parse_judge_json('{"done": 1.0}')["done"] is True
        assert parse_judge_json('{"done": 0.0}')["done"] is False

    def test_bare_example_then_fenced_verdict(self) -> None:
        """裸示例对象在前、fence 真实块在后时应取 fence 真实块。"""
        raw = (
            'example {"done": true} but the real answer is\n'
            '```json\n{"done": false, "reason": "fenced real"}\n```'
        )
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is False

    def test_verdict_inside_fence_after_fenced_example(self) -> None:
        """双 fence 中第一个是示例、第二个是真实判定时取第二个。"""
        raw = (
            '```json\n{"done": true, "reason": "example block"}\n```\n'
            'final:\n```json\n{"done": true, "reason": "real block"}\n```'
        )
        parsed = parse_judge_json(raw)
        assert parsed is not None
        assert parsed["done"] is True
        assert parsed["reason"] == "real block"
