# cognitive_map/

## Overview
Deterministic OKF cognitive map writers for `wiki/index.md`, `wiki/log.md`, `wiki/hot.md`, and `wiki/SCHEMA.md`.
Zero-LLM refresh after compile, maintain, import, pending approve, and repair-types events.
Hot context and recent log context are consumed only inside `WikiQueryEngine.query()` — not injected into agent system prompts.
Index context is consumed inside compile concept extraction — not injected into Turn1 agent tools.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Public exports for refresh service, events, and hot reader | ✅ |
| atomic_io.py | Core | Shared atomic text writes for cognitive map artifacts | ✅ |
| events.py | Types | `WikiMapEventType` enum (incl. `RAW_SUPERSEDE`) and `WikiMapEvent` dataclass for log entries | ✅ |
| snapshot.py | Core | Zero-LLM `HotSnapshot` builder and hot.md renderer; Key pages are the first five published pages (a draft or blocked page name stays out of the hot.md prefix of every `wiki_query` answer), the concept count covers every page | ✅ |
| writer.py | Core | Atomic index/log/hot writers (`index.md` lists published pages only), `read_hot_context`, `read_log_context`, stats helpers, refresh orchestration | ✅ |
| schema_writer.py | Core | `wiki/SCHEMA.md` SSOT writer + `read_index_context` for compile extraction | ✅ |
| index_routing.py | Core | Parse/score `wiki/index.md`; `INDEX_ROUTING_SECTION`; CJK-aware terms via retrieval tokenizer | ✅ |

## Key Dependencies

- `core.structure` (WikiStructure paths, sidecar helpers, concept listing)
- `core.frontmatter_contract` (page type grouping and the published-page reader for index.md and the hot.md key pages)
- `core.link_resolver` (vault-relative page names for the hot.md key pages)
