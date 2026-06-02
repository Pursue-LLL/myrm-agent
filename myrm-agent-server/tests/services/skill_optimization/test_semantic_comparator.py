"""Tests for SemanticComparator (Server layer)

Covers:
- Inherits StructuredComparator behavior
- LLM not triggered when is_match=True
- LLM not triggered when local_avg < 0.1
- LLM not triggered when local_avg >= threshold
- Weight configuration
"""

import pytest

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
