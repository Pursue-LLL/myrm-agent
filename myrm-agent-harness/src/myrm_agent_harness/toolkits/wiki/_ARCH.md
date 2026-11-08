# wiki/

## Overview
LLM-Wiki toolkit: Karpathy-architecture knowledge base engine. Compiles raw documents into
structured, cross-linked wiki articles with SHA256 incremental caching, FTS5+Qdrant hybrid
search, 3D knowledge graph with LPA community detection, knowledge drift defense, L0/L1
directory sidecars, bottom-up incremental DAG refresh, and LLM-driven wikilink enrichment.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Wiki toolkit entry point; also the server's import path for `fetch_url_markdown` and `SourceLoadError` | ✅ |
| wiki_agent_tools.py | Core | LangChain tool integration: **ingest/query/apply** agent tools (apply writes stage as HITL pending drafts, never publish directly); URL ingest via `pipeline/ingress/publish_url_markdown_ingress`; admin compile/maintain via REST. Auto-compile on ingest, knowledge compounding on query. Ingest sources are loaded by `source_loader`: a source with no readable text is refused with its reason (`Failed to ingest document: …`) and never written to raw/. | ✅ |
| wiki_tool_descriptions.py | Core | Bilingual (EN/ZH) descriptions of the three agent tools and their locale resolvers, shared by the LangChain tools and the MCP adapter. | ✅ |
| source_loader.py | Core | Source loading for ingestion: `fetch_url_markdown` (FetchEngine only — SSRF guard, tier degradation, subtitle extractors; a page with nothing readable raises `SourceLoadError`, and so does a URL the SSRF guard blocks, because the engine answers a blocked, timed-out or unreachable URL with no document), `read_local_file` (file parsers where one supports the format; otherwise UTF-8 text, refusing binary files, non-UTF-8 bytes, directories and empty files instead of decoding garbage), `looks_like_local_path` (the predicate both the ingest tool and the MCP adapter use). | ✅ |
| ingest_chunking.py | Core | `split_if_large`: cuts a document above the compile threshold into numbered chunk files next to its original path. | ✅ |
| mcp_server.py | Surface | MCP adapter exposing wiki tools (`wiki_query_tool`, `wiki_ingest_tool`, `wiki_apply_tool`) to external agents (Claude Code, Cursor) — thin shell over the LangChain tools via `register_wiki_mcp_tools` + request-level ContextVar; ingest is URL/raw-text only on this surface (local file paths refused with the same `looks_like_local_path` predicate the ingest tool uses). | ✅ |

| Submodule | Description |
|-----------|-------------|
| core/ | Config (purpose, compile strategy), types (ConceptInfo, WikiArticle, CompileResult, SourceSnippet, QueryResult, LintIssue/Result, WikiMetadata), 5-layer physical topology (raw/sources/knowledge/index/deliverables), link syntax SSOT (`link_extraction`: which links a page holds), link resolver SSOT (`link_resolver`: link target → page key, index identity), Related Concepts section SSOT (`related_links`: the one writer of a page's related links), source card contract (SourceCardContract), and parsers (LLM response → ConceptInfo) |
| maintenance/ | Linter: health checks, drift/stale detection, knowledge-gap analysis, LLM link enrichment (no LLM auto-write for incomplete articles) |
| diagnostics/ | Deterministic structural lint SSOT |
| pipeline/ | Compiler (parallel batch ingestion, SHA256 cache, auto-retry queue, **survey/** structure scan + facet seed carry-forward, compile phase SSE), **ingress/** (clip + URL markdown → raw_gate), **contradiction_synthesis/** (CCSP Step 2.5 evolution pages), sidecar builder (L0/L1 bottom-up DAG), cognitive_map (OKF index/log/hot writers), postprocess (backlink generation, metadata persistence), **apply/** (narrow-write SSOT; agent/chat callers stage pending), **raw_gate/** (raw publication gate SSOT), publication gate (WPG SSOT + deterministic fail-closed routing + stale guard + move reindex), pending edits (HITL stage/approve) |
| portability/ | Full vault ZIP export, local git auto-commit and Obsidian `.canvas` text extraction (`vault_archive`, `vault_git`, `obsidian_canvas`) |
| retrieval/ | Indexer (FTS5 hybrid search, one index row per page key, vector upsert/delete, sidecar tiered indexing, weighted graph edges whose targets are resolved to page keys), tokenizer (stemming FTS5 table tokenizer, CJK bigram FTS5 query builder), best_first (priority-queue convergence + raw_claim rerank), graph_store (BFS traversal, federated graph queries, insights), query engine (hot + recent log prefix, index/sidecar/FTS seeds → best-first converge, citation snippet extraction, asset hit fusion), asset_index (wiki/assets caption FTS5 + Qdrant + orphan purge) |

## Key Dependencies

- `web_fetch` (FetchEngine for URL ingestion with YouTube/Bilibili subtitle extraction + multi-tier fallback; its SSRF guard is the only network gate of URL ingestion)
- `file_parsers` (local PDF/Office/image parsing for file ingestion)
- `utils.content_sniff` (tells a binary file from text for files no parser supports)
- `utils` (logger, context_format)
- `web_search` (optional)
- `memory` (auto-archive from conversations)
- `vector` (Qdrant hybrid search)
- `retriever` (RRF fusion)
