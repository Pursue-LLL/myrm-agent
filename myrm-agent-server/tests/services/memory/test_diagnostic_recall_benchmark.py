"""Unit tests for diagnostic_recall_benchmark helper functions.

Covers _aggregate_category_stats, _build_categories_dict, _count_category_hits,
and MemoryCommandBenchmarkSummary construction in probe results.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.reliability import MemoryRecallBenchmarkResult

from app.schemas.memory.command_center import MemoryCommandBenchmarkSummary
from app.services.memory.diagnostic_recall_benchmark import (
    _aggregate_category_stats,
    _build_categories_dict,
    _count_category_hits,
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
