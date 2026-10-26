"""A stalled query embedding must not starve local recall of its time budget.

Embedding, BM25 and the stores share one wall-clock deadline. Without a reserve a
hung embedding endpoint ran the whole deadline out, so the local stores that were
supposed to answer the degraded search got no time and the search returned nothing.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_index import wrap_with_bm25_sparse_index
from myrm_agent_harness.toolkits.memory._internal.search_deadline import (
    LOCAL_RECALL_RESERVE_FRACTION,
    embedding_budget,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig, RetrievalConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

_TOTAL_SECONDS = 2.0


def test_embedding_budget_leaves_the_local_recall_reserve() -> None:
    deadline = perf_counter() + _TOTAL_SECONDS

    budget = embedding_budget(deadline, _TOTAL_SECONDS)

    expected = _TOTAL_SECONDS * (1 - LOCAL_RECALL_RESERVE_FRACTION)
    assert expected - 0.1 < budget <= expected
    assert budget < _TOTAL_SECONDS - 0.1, "a non-empty reserve must be withheld from the embedding"


def test_embedding_budget_is_zero_once_the_deadline_passed() -> None:
    assert embedding_budget(perf_counter() - 1.0, _TOTAL_SECONDS) == 0.0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_stalled_embedding_still_returns_local_keyword_hits(tmp_path: Path) -> None:
    from myrm_agent_harness.toolkits.vector.qdrant import create_embedded_store

    config = MemoryConfig(
        embedding_model="stalled-test-model",
        collection_prefix="reserve",
        retrieval=RetrievalConfig(timeout_seconds=_TOTAL_SECONDS),
    )
    store = await create_embedded_store(path=str(tmp_path / "qdrant"))
    wrapped = wrap_with_bm25_sparse_index(store)
    assert wrapped is not None
    try:
        embedding = AsyncMock()
        embedding.embed = AsyncMock(return_value=[0.1] * 8)
        embedding.embed_batch = AsyncMock(return_value=[[0.1] * 8])
        embedding.dimension = 8
        manager = MemoryManager(config, user_id="u1", vector=wrapped, embedding=embedding, auto_warmup=False)
        stored = await manager.store(
            SemanticMemory(id=str(uuid4()), user_id="u1", content="用户偏好 Vitest 作为默认测试框架")
        )

        async def _stall(*_args: object, **_kwargs: object) -> list[float]:
            await asyncio.sleep(60)
            return []

        embedding.embed.side_effect = _stall

        started = perf_counter()
        results = await manager.search("Vitest", memory_types=[MemoryType.SEMANTIC], limit=5, use_rrf=False)
        elapsed = perf_counter() - started

        assert [hit.memory.id for hit in results] == [stored.id]
        assert elapsed < _TOTAL_SECONDS
        trace = manager.last_retrieval_trace
        assert trace is not None
        assert trace.degraded is True
    finally:
        await wrapped.close()
