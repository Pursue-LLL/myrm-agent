"""Unit tests for diagnostic_recall_benchmark helper functions.

Covers _aggregate_category_stats, _build_categories_dict, _count_category_hits,
and MemoryCommandBenchmarkSummary construction in probe results.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.memory.reliability import MemoryRecallBenchmarkResult

from app.schemas.memory.command_center import MemoryCommandBenchmarkSummary
from app.services.memory.diagnostics.diagnostic.diagnostic_recall_benchmark import (
    _BENCHMARK_PAIRS,
    _aggregate_category_stats,
    _build_categories_dict,
    _count_category_hits,
    run_golden_recall_benchmark,
)


class TestAggregateCategoryStats:
    def test_empty_results(self) -> None:
        stats = _aggregate_category_stats([])
        assert stats == {}

    def test_single_category(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="c1", category="cjk", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c2", category="cjk", expected_found=False, score=0.0),
        ]
        stats = _aggregate_category_stats(results)
        assert stats == {"cjk": [True, False]}

    def test_multiple_categories(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="c1", category="arch", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c2", category="cjk", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c3", category="arch", expected_found=False, score=0.0),
        ]
        stats = _aggregate_category_stats(results)
        assert "arch" in stats
        assert "cjk" in stats
        assert stats["arch"] == [True, False]
        assert stats["cjk"] == [True]

    def test_fallback_to_case_id(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="fallback_case", category="", expected_found=True, score=1.0),
        ]
        stats = _aggregate_category_stats(results)
        assert "fallback_case" in stats


class TestBuildCategoriesDict:
    def test_empty(self) -> None:
        assert _build_categories_dict([]) == {}

    def test_all_pass(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="c1", category="arch", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c2", category="arch", expected_found=True, score=1.0),
        ]
        d = _build_categories_dict(results)
        assert d == {"arch": "2/2"}

    def test_mixed(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="c1", category="arch", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c2", category="arch", expected_found=False, score=0.0),
            MemoryRecallBenchmarkResult(case_id="c3", category="cjk", expected_found=True, score=1.0),
        ]
        d = _build_categories_dict(results)
        assert d["arch"] == "1/2"
        assert d["cjk"] == "1/1"


class TestCountCategoryHits:
    def test_format(self) -> None:
        results = [
            MemoryRecallBenchmarkResult(case_id="c1", category="arch", expected_found=True, score=1.0),
            MemoryRecallBenchmarkResult(case_id="c2", category="cjk", expected_found=False, score=0.0),
        ]
        text = _count_category_hits(results)
        assert "arch=1/1" in text
        assert "cjk=0/1" in text


class TestMemoryCommandBenchmarkSummary:
    def test_schema_defaults(self) -> None:
        s = MemoryCommandBenchmarkSummary()
        assert s.case_count == 0
        assert s.recall_at_k == 0.0
        assert s.top_k == 5
        assert s.categories == {}

    def test_schema_populated(self) -> None:
        s = MemoryCommandBenchmarkSummary(
            case_count=16,
            passed_count=16,
            recall_at_k=1.0,
            ndcg_at_k=1.0,
            mrr_score=1.0,
            precision_at_k=0.2,
            latency_p50_ms=12.0,
            latency_p95_ms=23.0,
            top_k=5,
            categories={"arch": "2/2", "cjk": "2/2"},
        )
        assert s.case_count == 16
        assert s.passed_count == 16
        assert s.categories["arch"] == "2/2"

    def test_serialization(self) -> None:
        s = MemoryCommandBenchmarkSummary(
            case_count=2,
            passed_count=1,
            recall_at_k=0.5,
            categories={"arch": "1/2"},
        )
        data = s.model_dump()
        assert data["case_count"] == 2
        assert data["categories"]["arch"] == "1/2"
        assert isinstance(data["latency_p50_ms"], float)


def test_benchmark_pairs_contain_longdoc_penetration() -> None:
    cases = {p.case_id: p for p in _BENCHMARK_PAIRS}
    assert "longdoc_head_zh" in cases
    assert "longdoc_tail_zh" in cases
    assert "adversarial_lockfile_override_zh" in cases
    assert "adversarial_deprecated_api_en" in cases
    assert cases["longdoc_tail_zh"].category == "longdoc_penetration"
    assert cases["adversarial_lockfile_override_zh"].category == "adversarial_conflict"
    assert "user_id % 128" in cases["longdoc_tail_zh"].content


@pytest.mark.asyncio
async def test_run_golden_recall_benchmark_no_vector() -> None:
    result = await run_golden_recall_benchmark(None, run_id="test_run_123")
    assert result.status == "missing"
    assert result.id == "golden_recall_benchmark"
    assert "skipped" in result.evidence


@pytest.mark.asyncio
async def test_run_golden_recall_benchmark_mock_manager() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory

    mock_manager = MagicMock()
    mock_manager.has_vector = True
    mock_manager.config = MagicMock()
    mock_manager.config.semantic_collection = "semantic_col"
    mock_manager.config.episodic_collection = "episodic_col"

    async def mock_store(mem: SemanticMemory | EpisodicMemory, **kwargs) -> SemanticMemory | EpisodicMemory:
        if isinstance(mem, SemanticMemory):
            return SemanticMemory(
                id=f"mem_{len(mem.content)}",
                content=mem.content,
                importance=mem.importance,
                tags=mem.tags,
                metadata=mem.metadata,
                language=mem.language,
            )
        else:
            return EpisodicMemory(
                id=f"mem_{len(mem.content)}",
                content=mem.content,
                event_type=mem.event_type,
                related_entities=mem.related_entities,
                importance=mem.importance,
                metadata=mem.metadata,
                language=mem.language,
            )

    mock_manager.store = AsyncMock(side_effect=mock_store)

    async def mock_search(query: str, **kwargs):
        return [
            MagicMock(
                id=f"mem_{len(query)}",
                content="sample benchmark hit content",
                score=0.95,
                source_path="benchmark.md",
            )
        ]

    mock_manager.search = AsyncMock(side_effect=mock_search)
    mock_manager.delete_memory = AsyncMock(return_value=True)

    result = await run_golden_recall_benchmark(mock_manager, run_id="test_run_456")
    assert result.status in ("ready", "degraded", "warning", "critical")
    assert result.id == "golden_recall_benchmark"
    assert "Golden recall:" in result.evidence
    assert result.benchmark_summary is not None
    assert result.benchmark_summary.case_count > 0
