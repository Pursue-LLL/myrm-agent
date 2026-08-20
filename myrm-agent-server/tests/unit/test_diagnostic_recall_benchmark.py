"""Unit test for server golden recall benchmark diagnostics."""

from __future__ import annotations

import pytest

from app.services.memory.diagnostics.diagnostic.diagnostic_recall_benchmark import (
    _BENCHMARK_PAIRS,
    run_golden_recall_benchmark,
)


def test_benchmark_pairs_contain_longdoc_penetration() -> None:
    cases = {p.case_id: p for p in _BENCHMARK_PAIRS}
    assert "longdoc_head_zh" in cases
    assert "longdoc_tail_zh" in cases
    assert cases["longdoc_tail_zh"].category == "longdoc_penetration"
    assert "user_id % 128" in cases["longdoc_tail_zh"].content


@pytest.mark.asyncio
async def test_run_golden_recall_benchmark_no_vector() -> None:
    result = await run_golden_recall_benchmark(None, run_id="test_run_123")
    assert result.status == "missing"
    assert result.id == "golden_recall_benchmark"
    assert "skipped" in result.evidence
