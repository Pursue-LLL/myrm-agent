"""bump_access_counts: one more use (count and last-use time) of each recalled memory reaches the store.

The dense store is a faithful double (``tests.support.dense_vector_store``): like
``QdrantVectorStore.upsert`` it refuses a document without its vector before writing anything,
and the embeddings-less BM25 mirror is the only copy of what it holds.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse.index import BM25SparseIndexStore
from myrm_agent_harness.toolkits.memory._internal.maintenance import bump_access_counts
from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    doc_to_episodic,
    doc_to_semantic,
    episodic_to_doc,
    semantic_to_doc,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemorySearchResult,
    MemoryType,
    ProceduralMemory,
    SemanticMemory,
)
from myrm_agent_harness.toolkits.vector.base import VectorDocument
from tests.support.dense_vector_store import DenseVectorStore

CONFIG = MemoryConfig(embedding_model="test")
STORED_VECTOR = [0.1, 0.2, 0.3]


class FailingStore(DenseVectorStore):
    async def upsert(self, collection: str, documents: Sequence[VectorDocument]) -> list[str]:
        raise RuntimeError("store unavailable")


def _semantic(memory_id: str, **fields: object) -> SemanticMemory:
    return SemanticMemory(id=memory_id, user_id="u1", content=f"fact {memory_id}", **fields)  # type: ignore[arg-type]


def _episodic(memory_id: str, **fields: object) -> EpisodicMemory:
    return EpisodicMemory(id=memory_id, user_id="u1", content=f"event {memory_id}", **fields)  # type: ignore[arg-type]


def _seed(store: DenseVectorStore, collection: str, memory: SemanticMemory | EpisodicMemory) -> VectorDocument:
    doc = semantic_to_doc(memory) if isinstance(memory, SemanticMemory) else episodic_to_doc(memory)
    doc.vector = list(STORED_VECTOR)
    return store.put(collection, doc)


def _hit(memory: SemanticMemory | EpisodicMemory | ProceduralMemory) -> MemorySearchResult:
    kinds = {SemanticMemory: MemoryType.SEMANTIC, EpisodicMemory: MemoryType.EPISODIC}
    return MemorySearchResult(memory=memory, score=0.9, memory_type=kinds.get(type(memory), MemoryType.PROCEDURAL))


def _stored_semantic(store: DenseVectorStore, memory_id: str) -> SemanticMemory:
    doc = store.stored(CONFIG.semantic_collection, memory_id)
    assert doc is not None, f"{memory_id} is gone from the store"
    return doc_to_semantic(doc)


def _stored_episodic(store: DenseVectorStore, memory_id: str) -> EpisodicMemory:
    doc = store.stored(CONFIG.episodic_collection, memory_id)
    assert doc is not None, f"{memory_id} is gone from the store"
    return doc_to_episodic(doc)


@pytest.mark.asyncio
async def test_dense_store_persists_the_use_of_hits_that_carry_no_vector() -> None:
    store = DenseVectorStore()
    semantic, episodic = _semantic("s1", access_count=2), _episodic("e1")
    _seed(store, CONFIG.semantic_collection, semantic)
    _seed(store, CONFIG.episodic_collection, episodic)

    await bump_access_counts([_hit(semantic.model_copy()), _hit(episodic.model_copy())], store, CONFIG)

    assert _stored_semantic(store, "s1").access_count == 3
    assert _stored_semantic(store, "s1").last_accessed_at is not None
    assert _stored_episodic(store, "e1").access_count == 1
    assert _stored_episodic(store, "e1").last_accessed_at is not None


@pytest.mark.asyncio
async def test_dense_store_one_vectorless_hit_does_not_drop_the_batch() -> None:
    store = DenseVectorStore()
    memories = [_semantic(f"s{i}") for i in range(3)]
    for memory in memories:
        _seed(store, CONFIG.semantic_collection, memory)
    with_vector = memories[1].model_copy(update={"embedding": list(STORED_VECTOR)})
    hits = [_hit(memories[0].model_copy()), _hit(with_vector), _hit(memories[2].model_copy())]

    await bump_access_counts(hits, store, CONFIG)

    assert [_stored_semantic(store, f"s{i}").access_count for i in range(3)] == [1, 1, 1]


@pytest.mark.asyncio
async def test_dense_store_keeps_what_changed_since_the_search() -> None:
    store = DenseVectorStore()
    recalled = _semantic("s1", importance=0.5)
    stored = _seed(store, CONFIG.semantic_collection, recalled)
    hit = recalled.model_copy(update={"embedding": list(STORED_VECTOR)})
    # Maintenance archives and re-rates the memory while the agent is still reading its search result.
    stored.metadata["archived"] = True
    stored.metadata["importance"] = 0.9

    await bump_access_counts([_hit(hit)], store, CONFIG)

    after = store.stored(CONFIG.semantic_collection, "s1")
    assert after is not None
    assert after.metadata["archived"] is True
    assert after.metadata["importance"] == 0.9
    assert after.metadata["access_count"] == 1


@pytest.mark.asyncio
async def test_dense_store_does_not_bring_back_a_point_deleted_since_the_search() -> None:
    store = DenseVectorStore()
    kept, gone = _semantic("s1"), _semantic("s2")
    _seed(store, CONFIG.semantic_collection, kept)

    await bump_access_counts([_hit(kept.model_copy()), _hit(gone.model_copy())], store, CONFIG)

    assert _stored_semantic(store, "s1").access_count == 1
    assert store.stored(CONFIG.semantic_collection, "s2") is None


@pytest.mark.asyncio
async def test_a_use_stamp_changes_neither_content_nor_update_time_nor_vector() -> None:
    store = DenseVectorStore()
    memory = _semantic("s1")
    before = _seed(store, CONFIG.semantic_collection, memory).model_copy(deep=True)

    await bump_access_counts([_hit(memory.model_copy())], store, CONFIG)

    after = store.stored(CONFIG.semantic_collection, "s1")
    assert after is not None
    assert (after.content, after.vector, after.updated_at) == (before.content, before.vector, before.updated_at)


@pytest.mark.asyncio
async def test_embeddings_less_store_writes_the_hits_to_its_only_copy() -> None:
    inner = AsyncMock()
    store = BM25SparseIndexStore(inner, sparse_authoritative=True)
    memory = _semantic("s1", access_count=4)

    await bump_access_counts([_hit(memory)], store, CONFIG)

    inner.upsert_sparse.assert_awaited_once()
    (_, points), _kwargs = inner.upsert_sparse.await_args
    assert points[0].id == "s1"
    assert points[0].metadata["access_count"] == 5
    assert points[0].metadata["last_accessed_at"]
    inner.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_hits_are_counted_in_memory_whatever_the_store_does() -> None:
    store = FailingStore()
    memory = _semantic("s1")
    _seed(store, CONFIG.semantic_collection, memory)

    await bump_access_counts([_hit(memory)], store, CONFIG)

    assert memory.access_count == 1
    assert memory.last_accessed_at is not None


@pytest.mark.asyncio
async def test_repeated_recalls_accumulate_in_the_store() -> None:
    store = DenseVectorStore()
    memory = _semantic("s1")
    _seed(store, CONFIG.semantic_collection, memory)
    hit = _hit(memory.model_copy())

    for _ in range(3):
        await bump_access_counts([hit], store, CONFIG)

    assert _stored_semantic(store, "s1").access_count == 3
    assert hit.memory.access_count == 3


@pytest.mark.asyncio
async def test_last_use_is_the_time_of_the_latest_recall() -> None:
    store = DenseVectorStore()
    memory = _semantic("s1", last_accessed_at=datetime(2026, 1, 1, tzinfo=UTC))
    _seed(store, CONFIG.semantic_collection, memory)

    await bump_access_counts([_hit(memory.model_copy())], store, CONFIG)

    last_use = _stored_semantic(store, "s1").last_accessed_at
    assert last_use is not None
    assert (datetime.now(UTC) - last_use).total_seconds() < 60


@pytest.mark.asyncio
async def test_procedural_rule_use_is_written_through_the_relational_store() -> None:
    relational = AsyncMock()
    rule = ProceduralMemory(
        id="p1", content="Always use TypeScript", trigger="new file", action="use .ts", source="agent_self"
    )

    await bump_access_counts([_hit(rule)], DenseVectorStore(), CONFIG, relational=relational)

    assert rule.access_count == 1
    assert rule.last_accessed_at is not None
    relational.update_rule.assert_awaited_once_with(rule.id, rule)


@pytest.mark.asyncio
async def test_procedural_rule_is_skipped_without_a_relational_store() -> None:
    rule = ProceduralMemory(id="p1", content="rule", trigger="t", action="a", source="agent_self")

    await bump_access_counts([_hit(rule)], DenseVectorStore(), CONFIG, relational=None)

    assert rule.access_count == 0


@pytest.mark.asyncio
async def test_a_failing_rule_update_does_not_propagate() -> None:
    relational = AsyncMock()
    relational.update_rule.side_effect = RuntimeError("DB connection lost")
    rule = ProceduralMemory(id="p1", content="rule", trigger="t", action="a", source="agent_self")

    await bump_access_counts([_hit(rule)], DenseVectorStore(), CONFIG, relational=relational)

    assert rule.access_count == 1
    relational.update_rule.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_three_types_are_tracked_in_one_call() -> None:
    store, relational = DenseVectorStore(), AsyncMock()
    semantic, episodic = _semantic("s1"), _episodic("e1")
    rule = ProceduralMemory(id="p1", content="rule", trigger="t", action="a", source="agent_self")
    _seed(store, CONFIG.semantic_collection, semantic)
    _seed(store, CONFIG.episodic_collection, episodic)

    await bump_access_counts(
        [_hit(semantic.model_copy()), _hit(episodic.model_copy()), _hit(rule)], store, CONFIG, relational=relational
    )

    assert _stored_semantic(store, "s1").access_count == 1
    assert _stored_episodic(store, "e1").access_count == 1
    assert rule.access_count == 1
    relational.update_rule.assert_awaited_once()
