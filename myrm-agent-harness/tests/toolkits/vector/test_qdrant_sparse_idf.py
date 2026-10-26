"""Qdrant sparse mirror IDF weighting on an embedded store.

A rare term must outweigh a term every document contains, both for a mirror
created now and for one created before the modifier existed (upgraded in place).
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from qdrant_client import models

from myrm_agent_harness.toolkits.vector.base import SparsePoint
from myrm_agent_harness.toolkits.vector.qdrant import create_embedded_store
from myrm_agent_harness.toolkits.vector.qdrant.sparse import BM25_SPARSE_VECTOR_NAME, QdrantSparseMixin

# Token ids stand in for hashed terms: 1 = "user" (in every document), 2 = "kubernetes" (in one).
COMMON, RARE, FILLER, EXTRA = 1, 2, 3, 4
NOW = datetime(2026, 1, 1, tzinfo=UTC)
COLLECTION = "mirror_bm25"


def _point(pid: str, terms: dict[int, float]) -> SparsePoint:
    indices = sorted(terms)
    return SparsePoint(
        id=pid,
        indices=indices,
        values=[terms[i] for i in indices],
        content=pid,
        metadata={"user_id": "u1"},
        created_at=NOW,
        updated_at=NOW,
    )


# "heavy" repeats the common term (saturated tf 1 + ln 4); "rare" has the discriminative term once.
POINTS = [
    _point("heavy", {COMMON: 1.0 + math.log(4), EXTRA: 1.0}),
    _point("rare", {COMMON: 1.0, RARE: 1.0, FILLER: 1.0}),
    _point("plain-a", {COMMON: 1.0}),
    _point("plain-b", {COMMON: 1.0}),
]


async def _ranking(store: QdrantSparseMixin) -> list[str]:
    hits = await store.search_sparse(COLLECTION, [COMMON, RARE], [1.0, 1.0], limit=4)
    return [h.document.id for h in hits]


async def _modifier(store: QdrantSparseMixin) -> models.Modifier | None:
    info = await store._execute(store._client.get_collection, collection_name=COLLECTION)  # type: ignore[attr-defined]
    params = cast("models.CollectionInfo", info).config.params.sparse_vectors or {}
    return params[BM25_SPARSE_VECTOR_NAME].modifier


async def _create_without_modifier(store: QdrantSparseMixin) -> None:
    """Create a mirror the way earlier releases did: no IDF modifier."""
    await store._execute(
        store._client.create_collection,  # type: ignore[attr-defined]
        collection_name=COLLECTION,
        sparse_vectors_config={
            BM25_SPARSE_VECTOR_NAME: models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))
        },
    )


class TestSparseIdf:
    @pytest.mark.asyncio
    async def test_new_mirror_ranks_the_rare_term_first(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        try:
            assert await store.ensure_sparse_collection(COLLECTION) is True
            await store.upsert_sparse(COLLECTION, POINTS)

            assert await _modifier(store) == models.Modifier.IDF
            assert (await _ranking(store))[0] == "rare"
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_old_mirror_is_upgraded_in_place_and_keeps_its_points(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        try:
            await _create_without_modifier(store)
            await store.upsert_sparse(COLLECTION, POINTS)
            assert (await _ranking(store))[0] == "heavy"

            assert await store.upgrade_sparse_idf(COLLECTION) is True

            assert await _modifier(store) == models.Modifier.IDF
            ranking = await _ranking(store)
            assert ranking[0] == "rare"
            assert sorted(ranking) == ["heavy", "plain-a", "plain-b", "rare"]
            assert await store.upgrade_sparse_idf(COLLECTION) is False
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_upgrade_never_creates_a_missing_mirror(self, tmp_path: Path) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        try:
            assert await store.upgrade_sparse_idf(COLLECTION) is False
            assert await store.sparse_collection_ready(COLLECTION) is False
        finally:
            await store.close()

    @pytest.mark.asyncio
    async def test_rejected_upgrade_is_fail_open(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store = await create_embedded_store(path=str(tmp_path / "qdrant"))
        try:
            await _create_without_modifier(store)
            await store.upsert_sparse(COLLECTION, POINTS)

            def reject(**_: object) -> None:
                raise RuntimeError("modifier updates unsupported")

            monkeypatch.setattr(store._client, "update_collection", reject)  # type: ignore[attr-defined]

            assert await store.upgrade_sparse_idf(COLLECTION) is False
            assert await _modifier(store) is None
            assert (await _ranking(store))[0] == "heavy"
        finally:
            await store.close()
