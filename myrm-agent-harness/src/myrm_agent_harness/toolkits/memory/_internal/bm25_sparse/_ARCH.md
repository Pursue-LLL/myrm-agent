# Architecture - bm25_sparse

Persistent BM25 sparse mirror of the semantic / episodic memory collections.

## Module Role

Keyword recall for memory: every dense write is mirrored fail-open into a `{collection}_bm25` sparse collection, and BM25 queries are answered from that persisted index (server-side IDF) instead of a per-query corpus scroll. Encoding, the query pipeline and the wrapper that owns the mirror lifecycle live here; the corpus-scroll fallback for backends without sparse support stays in `../storage_search.py`.

## File Manifest

| File | Tier | Responsibility | Tested |
|------|------|----------------|--------|
| `__init__.py` | Facade | Domain facade: the mirror wrapper and its capability helpers, collection naming and encoding, and `bm25_scope`. The rest of `memory/` imports from here. | ✅ |
| `encoding.py` | Core | Hash-based sparse encoding for the BM25 mirror. Token hashing (crc32 u31), saturated term-frequency vectors (`1 + ln(tf)`), sparse collection naming (`_bm25`), and the dense-document → sparse-point conversion. Query encoding prunes function words before hashing (`query_terms`); stored documents keep their full token stream. Pure functions, no I/O: the mirror's write and query paths share one canonical tokenization. | ✅ |
| `index.py` | Core | Persistent BM25 sparse mirror lifecycle. The `BM25SparseIndexStore` wrapper fail-open mirrors every upsert/delete into a `{collection}_bm25` sparse collection and serves BM25 queries from it after a one-shot backfill; the first sparse query enables IDF weighting on mirrors that predate the modifier; `sparse_authoritative` routes the dense-surface reads, counts and writes (get / scroll / count / upsert / delete) to the mirror for embeddings-less deployments. `wrap_with_bm25_sparse_index` decides capability by exact `isinstance` at assembly time; legacy backends stay unwrapped on the corpus-scroll fallback path. `unwrap_sparse_mirror` returns the backend beneath the wrapper for the named-vector conversation collection, which the mirror does not cover; `is_sparse_authoritative` reports an embeddings-less store so a content rewrite can skip the dense embedding. | ✅ |
| `query.py` | Core | Fan-out BM25 query pipeline over the sparse mirrors. `bm25_scope` narrows a request to the mirror-covered types; only those mirrors are queried (in parallel), fused by raw score and max-normalized against the head hit, so the top-k cut never drops a requested-type hit in favour of a filtered-out one; `None` means the backend failed (caller degrades to the corpus-scroll path), `[]` means no match. Readiness and warmup stay with the wrapper. | ✅ |
| `query_terms.py` | Core | Query-side function-word pruning for the sparse BM25 mirror: English and Chinese closed-class words plus conversational fillers are dropped from sentence-length queries (5+ tokens; shorter queries are keyword queries and stay untouched), falling back to the original tokens when nothing else is left. Negations and name-like homographs stay. Not used by the legacy corpus-scroll path, which already selects long-query terms by corpus IDF. | ✅ |

## Design Invariants

1. **One tokenization**: the write and query paths share the encoding in `encoding.py`; only the query side prunes function words, stored documents keep their full token stream.
2. **Fail-open**: a broken mirror never blocks dense writes; the query pipeline returns `None` when the backend failed (the caller degrades to the corpus-scroll path) and `[]` when nothing matched.
3. **Capability by exact type**: `wrap_with_bm25_sparse_index` decides at assembly time with `isinstance`; legacy backends stay unwrapped.
