# protocols/

## Overview
Storage-agnostic protocols for the memory system.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Storage-agnostic protocols for the memory system. | — |
| cache.py | Core | Embedding cache protocol — optional caching layer. | ✅ |
| conversation_search.py | Core | Storage-agnostic conversation search provider protocol consumed by the recall tool. | ✅ |
| embedding.py | Core | Embedding protocol — text to vector abstraction. | ✅ |
| graph.py | Core | Memory-system graph store protocol。Defines the graph operation interface required by the memory module, including list_nodes/list_relationships/get_stats for visualization, exports GraphNode, GraphRelationship, GraphStats | ✅ |
| relational.py | Core | Relational store protocol. Defines the relational storage interface for Profile, Procedural and Pending memories, the exact-fact / full-text index and the integrity check. | ✅ |
| vector.py | Core | Memory-system vector store protocol. Defines the vector operation interface required by the memory module, including `is_persistent` (persistence introspection so the memory layer can surface `:memory:`-degraded backends) and `backfill_payload_copy` (copy one payload field into another on the documents that lack it; a backend that cannot rewrite a payload in place copies nothing), exports VectorStoreProtocol, VectorDocument, VectorSearchResult | ✅ |
