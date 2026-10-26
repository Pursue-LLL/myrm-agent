"""BM25 sparse mirror: persistent keyword index beside the dense memory collections.

[INPUT]
- memory._internal.bm25_sparse.encoding::* (POS: hash-based sparse encoding and mirror collection naming)
- memory._internal.bm25_sparse.index::* (POS: mirror lifecycle wrapper and capability helpers)
- memory._internal.bm25_sparse.query::bm25_scope (POS: memory types the mirror covers)

[OUTPUT]
- BM25SparseIndexStore / wrap_with_bm25_sparse_index / unwrap_sparse_mirror / is_sparse_authoritative: mirror wrapper and its capability helpers
- BM25_COLLECTION_SUFFIX / bm25_collection_for / content_to_sparse: sparse mirror naming and encoding
- bm25_scope: the memory types the mirror covers

[POS]
Facade of the BM25 sparse-mirror domain; the rest of ``memory/`` imports from here and never from the submodules.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._internal.bm25_sparse.encoding import (
    BM25_COLLECTION_SUFFIX,
    bm25_collection_for,
    content_to_sparse,
)
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse.index import (
    BM25SparseIndexStore,
    is_sparse_authoritative,
    unwrap_sparse_mirror,
    wrap_with_bm25_sparse_index,
)
from myrm_agent_harness.toolkits.memory._internal.bm25_sparse.query import bm25_scope

__all__ = [
    "BM25_COLLECTION_SUFFIX",
    "BM25SparseIndexStore",
    "bm25_collection_for",
    "bm25_scope",
    "content_to_sparse",
    "is_sparse_authoritative",
    "unwrap_sparse_mirror",
    "wrap_with_bm25_sparse_index",
]
