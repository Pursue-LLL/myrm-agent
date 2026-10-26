"""BM25 Sparse Query — the mirror's fan-out query pipeline.

[INPUT]
- memory.protocols.vector::{VectorStoreProtocol, VectorDocument} (POS: vector protocol)
- memory.config::MemoryConfig (POS: collection names, bm25_top_k)
- memory._internal.bm25_sparse_encoding::{bm25_collection_for, query_to_sparse} (POS: sparse encoding)
- memory._internal.storage_converters::{_user_filter, doc_to_episodic, doc_to_semantic} (POS: converters)
- memory.types::{MemorySearchResult, MemoryType} (POS: memory data models)

[OUTPUT]
- BM25_MEMORY_TYPES / bm25_scope: the memory types the mirror covers, and a
  request narrowed to them
- run_bm25_search: BM25 query over the requested semantic / episodic sparse
  mirrors, fused by raw score and max-normalized against the head hit

[POS]
Query half of the persistent BM25 mirror. Runs the requested sparse collections
in parallel and keeps query logic out of the wrapper: only mirrors of the
requested types are queried, so the head-hit truncation never discards a hit of
a requested type in favour of one that is filtered out later. ``None`` means the
backend failed (the caller degrades to the corpus-scroll path), ``[]`` means the
query tokenizes to nothing or no document matches. Readiness and warmup stay
with the wrapper.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Final

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse_encoding import (
    bm25_collection_for,
    query_to_sparse,
)
from myrm_agent_harness.toolkits.memory._internal.storage_converters import (
    _user_filter,
    doc_to_episodic,
    doc_to_semantic,
)
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument, VectorStoreProtocol
from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemorySearchResult,
    MemoryType,
    SemanticMemory,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig

logger = logging.getLogger(__name__)

_CONVERTERS: Final[dict[MemoryType, Callable[[VectorDocument], SemanticMemory | EpisodicMemory]]] = {
    MemoryType.SEMANTIC: doc_to_semantic,
    MemoryType.EPISODIC: doc_to_episodic,
}

# The mirror covers these types only; profile, procedural and conversation memories live elsewhere.
BM25_MEMORY_TYPES: Final[tuple[MemoryType, ...]] = tuple(_CONVERTERS)


def bm25_scope(memory_types: Sequence[MemoryType] | None) -> list[MemoryType]:
    """The mirror-covered types within a request (every covered type when unrestricted)."""
    return [t for t in BM25_MEMORY_TYPES if memory_types is None or t in memory_types]


async def run_bm25_search(
    inner: VectorStoreProtocol,
    query: str,
    config: MemoryConfig,
    *,
    memory_types: Sequence[MemoryType] | None = None,
    limit: int | None = None,
    namespaces: list[str] | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[MemorySearchResult] | None:
    """Fan a BM25 query out over the requested sparse mirrors of a sparse-capable backend.

    ``memory_types`` narrows the fan-out to those mirrors (default: every covered
    type). Returns ``None`` when the query tokenizes to nothing or the backend
    fails so the caller can fall back to the corpus-scroll path; ``[]`` when no
    requested type has a matching document.
    """
    searched = bm25_scope(memory_types)
    if not searched:
        return []
    indices, values = query_to_sparse(query)
    if not indices:
        return None

    filters = _user_filter(namespaces=namespaces, since=since, until=until)
    top_k = limit if limit is not None else config.bm25_top_k

    collections = {
        MemoryType.SEMANTIC: config.semantic_collection,
        MemoryType.EPISODIC: config.episodic_collection,
    }

    async def search_one(memory_type: MemoryType) -> list[tuple[float, VectorDocument, MemoryType]]:
        results = await inner.search_sparse(  # type: ignore[attr-defined]
            bm25_collection_for(collections[memory_type]),
            indices,
            values,
            limit=top_k,
            filters=filters,
        )
        return [(r.score, r.document, memory_type) for r in results]

    # The requested mirrors are queried in parallel, mirroring the legacy dual-scroll.
    try:
        outcomes = await asyncio.gather(*(search_one(t) for t in searched))
    except Exception as exc:
        logger.warning("BM25 sparse search degraded (non-fatal): %s", exc)
        return None
    hits = [hit for outcome in outcomes for hit in outcome]

    if not hits:
        return []

    hits.sort(key=lambda h: h[0], reverse=True)
    hits = hits[:top_k]
    normalizer = hits[0][0] if hits[0][0] > 0 else 1.0
    converted: list[MemorySearchResult] = []
    for score, doc, memory_type in hits:
        converted.append(
            MemorySearchResult(
                memory=_CONVERTERS[memory_type](doc),
                score=min(score / normalizer, 1.0),
                memory_type=memory_type,
            )
        )
    return converted
