"""Tests for Locomo v2 memory benchmark adapter."""

import pytest

from app.core.eval.benchmarks import (
    benchmark_needs_judge,
    build_benchmark_cases,
    list_benchmark_sources,
)
from app.core.eval.locomo import (
    build_locomo_cases,
    ensure_locomo_source,
    list_locomo_source,
)


def test_list_locomo_source():
    source = list_locomo_source()
    assert source["is_available"] is True
    assert source["task_count"] >= 10
    assert source["supports_memory_ab"] is True
    assert "source_path" in source


@pytest.mark.asyncio
async def test_ensure_locomo_source():
    progress_calls = []

    def on_progress(pct: float, msg: str):
        progress_calls.append((pct, msg))

    path = await ensure_locomo_source(on_progress=on_progress)
    assert path.exists()
    assert len(progress_calls) >= 2


def test_build_locomo_cases_full():
    cases, seed_map, is_sampled = build_locomo_cases(limit=0)
    assert len(cases) == 10
    assert not is_sampled
    assert len(seed_map) == 10

    # Verify structure of first case
    case = cases[0]
    assert case.metadata["id"] == "locomo-01-strict-ts"
    assert len(case.turns) == 3
    final_turn = case.turns[-1]
    assert len(final_turn.semantic_assertions) == 1
    assert "TypeScript" in final_turn.message or "rule" in final_turn.message


def test_build_locomo_cases_sampling():
    cases, seed_map, is_sampled = build_locomo_cases(limit=3, sample_seed=123)
    assert len(cases) == 3
    assert is_sampled is True
    assert len(seed_map) == 3


def test_benchmarks_catalog_integration():
    sources = list_benchmark_sources()
    locomo_entry = next((s for s in sources if s.get("benchmark_id") == "locomo"), None)
    assert locomo_entry is not None
    assert locomo_entry["supports_memory_ab"] is True
    assert locomo_entry["task_count"] >= 10

    # Build via unified interface
    cases, seeds, is_sampled = build_benchmark_cases("locomo", limit=2)
    assert len(cases) == 2
    assert is_sampled is True
    assert benchmark_needs_judge("locomo") is True
