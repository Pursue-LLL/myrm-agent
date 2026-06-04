"""Context search service unit tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.context.context_search_service import ContextSearchService, _rrf_merge, _RankedCandidate


def test_rrf_merge_prefers_both_lists() -> None:
    merged = _rrf_merge(
        [
            [
                _RankedCandidate(
                    key="memory:1",
                    source="memory",
                    title="memory",
                    snippet="supplier project",
                    reference="1",
                    rank=0,
                )
            ],
            [
                _RankedCandidate(
                    key="file:a",
                    source="workspace_file",
                    title="/docs/a.xlsx",
                    snippet="supplier table",
                    reference="/docs/a.xlsx",
                    rank=0,
                )
            ],
        ],
        top_k=2,
    )
    assert len(merged) == 2
    keys = {item.key for item in merged}
    assert "memory:1" in keys
    assert "file:a" in keys


@pytest.mark.asyncio
async def test_context_search_service_memory_only() -> None:
    memory_manager = MagicMock()
    result = MagicMock()
    result.id = "mem-1"
    result.memory_type.value = "semantic"
    result.content = "supplier notes"
    memory_manager.search = AsyncMock(return_value=[result])

    service = ContextSearchService(memory_manager=memory_manager, file_engine=None)
    response = await service.search("supplier", top_k=5)
    assert response.memory_count == 1
    assert response.file_count == 0
    assert len(response.hits) == 1
    assert response.hits[0].source == "memory"
