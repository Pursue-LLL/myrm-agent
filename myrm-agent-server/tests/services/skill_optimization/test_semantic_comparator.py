"""Tests for SemanticComparator (Server layer)

Covers:
- Inherits StructuredComparator behavior
- LLM not triggered when is_match=True
- LLM not triggered when local_avg < 0.1
- LLM not triggered when local_avg >= threshold
- Weight configuration
"""

import pytest

from app.core.utils.chat_utils import parse_llm_json_object
from app.services.skill_optimization.semantic_comparator import SemanticComparator


@pytest.mark.asyncio
async def test_identical_inputs_skip_llm() -> None:
    comp = SemanticComparator(model="test-model")
    result = await comp.compare(
        {"status": "ok", "result": "hello"},
        {"status": "ok", "result": "hello"},
    )
    assert result.is_match is True
    assert result.similarity_score == 1.0
    assert "LLM" not in result.diff_summary


@pytest.mark.asyncio
async def test_completely_different_skip_llm() -> None:
    comp = SemanticComparator(model="test-model")
    result = await comp.compare(
        {"a": "completely different content here"},
        {"z": "totally unrelated stuff there"},
    )
    assert result.is_match is False
    assert "LLM" not in result.diff_summary


@pytest.mark.asyncio
async def test_high_similarity_skip_llm() -> None:
    comp = SemanticComparator(
        model="test-model",
        match_threshold=0.99,
        llm_trigger_threshold=0.7,
    )
    result = await comp.compare(
        {"status": "ok", "result": "almost the same text content"},
        {"status": "ok", "result": "almost the same text content!"},
    )
    assert "LLM" not in result.diff_summary


@pytest.mark.asyncio
async def test_weight_normalization() -> None:
    comp = SemanticComparator(
        structural_weight=0.3,
        textual_weight=0.3,
        semantic_weight=0.4,
    )
    assert comp._s_weight + comp._t_weight + comp._sem_weight == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_inherits_structured_behavior() -> None:
    comp = SemanticComparator()
    result = await comp.compare({}, {})
    assert result.similarity_score == 1.0
    assert result.is_match is True


@pytest.mark.asyncio
async def test_one_side_empty() -> None:
    comp = SemanticComparator()
    result = await comp.compare({"key": "value"}, {})
    assert result.similarity_score == 0.0
    assert result.is_match is False


@pytest.mark.asyncio
async def test_parse_judge_json_plain() -> None:
    parsed = parse_llm_json_object('{"score": 0.95, "reasoning": "identical"}')
    assert parsed == {"score": 0.95, "reasoning": "identical"}


@pytest.mark.asyncio
async def test_parse_judge_json_unescaped_newline_in_string() -> None:
    """reasoning 字段内裸换行（minimax 等 reasoning 模型输出）不应导致解析失败。"""
    raw = '{"score": 0.95, "reasoning": "the only difference is\\na wording choice"}'
    parsed = parse_llm_json_object(raw)
    assert parsed is not None
    assert parsed["score"] == pytest.approx(0.95)
    assert "a wording choice" in str(parsed["reasoning"])


@pytest.mark.asyncio
async def test_parse_judge_json_pretty_printed() -> None:
    raw = '{\n  "score": 0.9,\n  "reasoning": "ok"\n}'
    parsed = parse_llm_json_object(raw)
    assert parsed is not None
    assert parsed["score"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_parse_judge_json_markdown_fence() -> None:
    raw = '```json\n{"score": 1.0, "reasoning": "same"}\n```'
    parsed = parse_llm_json_object(raw)
    assert parsed == {"score": 1.0, "reasoning": "same"}


@pytest.mark.asyncio
async def test_parse_judge_json_garbage_returns_none() -> None:
    assert parse_llm_json_object("hello world, not json at all") is None
    assert parse_llm_json_object("") is None


@pytest.mark.asyncio
async def test_parse_llm_json_object_structural_whitespace_preserved() -> None:
    """结构性空白必须保留，仅字符串字面量内的裸换行被转义。"""
    src = '{\n  "reasoning": "line one\nline two"\n}'
    parsed = parse_llm_json_object(src)
    assert parsed is not None
    assert parsed["reasoning"] == "line one\nline two"


@pytest.mark.asyncio
async def test_parse_llm_json_object_prose_framing() -> None:
    """judge 输出带前后缀文字时仍能提取对象。"""
    raw = 'Analysis complete. {"score": 0.8, "reasoning": "close"} Done.'
    parsed = parse_llm_json_object(raw)
    assert parsed is not None
    assert parsed["score"] == pytest.approx(0.8)
