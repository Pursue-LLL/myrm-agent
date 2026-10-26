"""BM25 retrieval honours the requested memory types before it truncates.

The mirror fan-out queries only the mirrors of the requested types. Querying every
mirror regardless would let the top-k cut drop a hit of a requested type in favour of
one that is filtered out later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_index import (
    BM25SparseIndexStore,
    wrap_with_bm25_sparse_index,
)
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_query import bm25_scope
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemoryType, SemanticMemory
from myrm_agent_harness.toolkits.vector.qdrant import create_embedded_store

CONFIG = MemoryConfig(embedding_model="test-model", collection_prefix="ts")


def _doc(content: str, memory_type: str) -> VectorDocument:
    now = datetime.now(UTC)
    return VectorDocument(
        id=str(uuid4()),
        content=content,
        vector=[0.1] * 8,
        metadata={"user_id": "u1", "memory_type": memory_type, "archived": False},
        created_at=now,
        updated_at=now,
    )


class TestBm25Scope:
    def test_unrestricted_request_covers_both_mirrors(self) -> None:
        assert bm25_scope(None) == [MemoryType.SEMANTIC, MemoryType.EPISODIC]

    def test_request_is_narrowed_to_covered_types(self) -> None:
        assert bm25_scope([MemoryType.EPISODIC, MemoryType.CONVERSATION]) == [MemoryType.EPISODIC]
        assert bm25_scope([MemoryType.CONVERSATION, MemoryType.PROFILE]) == []


class TestMirrorTypeScope:
    @pytest.mark.asyncio
    async def test_requested_type_survives_the_top_k_cut(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        wrapped = wrap_with_bm25_sparse_index(store)
        assert isinstance(wrapped, BM25SparseIndexStore)
        try:
            await wrapped.upsert(CONFIG.semantic_collection, [_doc("kubernetes upgrade plan", "semantic")])
            # Scores higher than the semantic hit: it would take the only top-1 slot.
            await wrapped.upsert(
                CONFIG.episodic_collection,
                [_doc("kubernetes upgrade kubernetes upgrade kubernetes", "episodic")],
            )
            await wrapped.bm25_backfill(CONFIG)

            semantic = await wrapped.bm25_search(
                "kubernetes upgrade", CONFIG, memory_types=[MemoryType.SEMANTIC], limit=1
            )
            episodic = await wrapped.bm25_search(
                "kubernetes upgrade", CONFIG, memory_types=[MemoryType.EPISODIC], limit=1
            )
            both = await wrapped.bm25_search("kubernetes upgrade", CONFIG, limit=1)

            assert semantic is not None and [h.memory_type for h in semantic] == [MemoryType.SEMANTIC]
            assert episodic is not None and [h.memory_type for h in episodic] == [MemoryType.EPISODIC]
            assert both is not None and [h.memory_type for h in both] == [MemoryType.EPISODIC]
        finally:
            await wrapped.close()

    @pytest.mark.asyncio
    async def test_type_the_mirror_does_not_cover_searches_nothing(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        wrapped = wrap_with_bm25_sparse_index(store)
        assert isinstance(wrapped, BM25SparseIndexStore)
        try:
            await wrapped.upsert(CONFIG.semantic_collection, [_doc("kubernetes upgrade plan", "semantic")])
            await wrapped.bm25_backfill(CONFIG)

            assert await wrapped.bm25_search("kubernetes", CONFIG, memory_types=[MemoryType.CONVERSATION]) == []
        finally:
            await wrapped.close()


class TestKeywordModeTypeFilter:
    @pytest.mark.asyncio
    async def test_search_returns_only_the_requested_type(self, tmp_path: Path) -> None:
        manager = await create_local_memory_manager(tmp_path / "mem", None)
        try:
            await manager.store(
                SemanticMemory(id=str(uuid4()), user_id="sandbox_user", content="kubernetes cluster upgrade plan")
            )
            await manager.store(
                EpisodicMemory(
                    id=str(uuid4()),
                    user_id="sandbox_user",
                    content="kubernetes cluster upgrade happened yesterday",
                    event_summary="k8s upgrade",
                )
            )

            async def types_for(requested: list[MemoryType] | None) -> set[MemoryType]:
                results = await manager.search("kubernetes upgrade", memory_types=requested, limit=10)
                return {r.memory_type for r in results}

            assert await types_for([MemoryType.SEMANTIC]) == {MemoryType.SEMANTIC}
            assert await types_for([MemoryType.EPISODIC]) == {MemoryType.EPISODIC}
            assert await types_for(None) == {MemoryType.SEMANTIC, MemoryType.EPISODIC}
        finally:
            await manager.close()
