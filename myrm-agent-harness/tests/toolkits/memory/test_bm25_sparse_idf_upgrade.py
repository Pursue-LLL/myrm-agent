"""The first sparse query brings mirrors written before the IDF modifier up to date."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from qdrant_client import models

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_encoding import bm25_collection_for
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_index import (
    BM25SparseIndexStore,
    wrap_with_bm25_sparse_index,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument
from myrm_agent_harness.toolkits.vector.qdrant import create_embedded_store
from myrm_agent_harness.toolkits.vector.qdrant.sparse import BM25_SPARSE_VECTOR_NAME

CONFIG = MemoryConfig(embedding_model="test-model", collection_prefix="idf")


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


async def _create_mirror_without_modifier(store: object, collection: str) -> None:
    """Create a mirror the way earlier releases did: no IDF modifier."""
    await store._execute(  # type: ignore[attr-defined]
        store._client.create_collection,  # type: ignore[attr-defined]
        collection_name=bm25_collection_for(collection),
        sparse_vectors_config={
            BM25_SPARSE_VECTOR_NAME: models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
        },
    )


async def _modifier(store: object, collection: str) -> models.Modifier | None:
    info = await store._execute(store._client.get_collection, collection_name=bm25_collection_for(collection))  # type: ignore[attr-defined]
    params = cast("models.CollectionInfo", info).config.params.sparse_vectors or {}
    return params[BM25_SPARSE_VECTOR_NAME].modifier


class TestMirrorIdfUpgrade:
    @pytest.mark.asyncio
    async def test_first_query_upgrades_both_mirrors_and_ranks_by_rarity(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        wrapped = wrap_with_bm25_sparse_index(store)
        assert isinstance(wrapped, BM25SparseIndexStore)
        try:
            for collection in (CONFIG.semantic_collection, CONFIG.episodic_collection):
                await _create_mirror_without_modifier(store, collection)

            rare = _doc("user kubernetes cluster", "semantic")
            await wrapped.upsert(
                CONFIG.semantic_collection,
                [
                    _doc("user user user user note", "semantic"),
                    rare,
                    _doc("user plain a", "semantic"),
                    _doc("user plain b", "semantic"),
                ],
            )
            await wrapped.upsert(CONFIG.episodic_collection, [_doc("user episode", "episodic")])
            await wrapped.bm25_backfill(CONFIG)
            assert await _modifier(store, CONFIG.semantic_collection) is None
            assert await _modifier(store, CONFIG.episodic_collection) is None

            hits = await wrapped.bm25_search("user kubernetes", CONFIG)

            assert hits is not None
            assert hits[0].memory.content == rare.content
            assert await _modifier(store, CONFIG.semantic_collection) == models.Modifier.IDF
            assert await _modifier(store, CONFIG.episodic_collection) == models.Modifier.IDF
        finally:
            await wrapped.close()
