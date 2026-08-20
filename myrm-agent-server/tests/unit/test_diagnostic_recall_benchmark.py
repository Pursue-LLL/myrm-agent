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


@pytest.mark.asyncio
async def test_run_golden_recall_benchmark_mock_manager() -> None:
    from unittest.mock import AsyncMock, MagicMock
    from myrm_agent_harness.toolkits.memory.types import SemanticMemory, EpisodicMemory

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



