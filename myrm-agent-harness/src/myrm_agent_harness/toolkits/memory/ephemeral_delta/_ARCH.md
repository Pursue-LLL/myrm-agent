# ephemeral_delta/

## Overview

Session-scoped tail deltas for cache-safe mid-chat recency; in-memory buffer with SQLite persistence on `memory.db` for process restart recovery.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Prompt-cache-preserving ephemeral session delta memory suite. | ✅ |
| `delta_store.py` | Core | Session buffer + hydrate; append/clear syncs optional persistence. | ✅ |
| `sqlite_persistence.py` | Core | WAL SQLite table on memory.db for restart-safe session deltas. | ✅ |
| `models.py` | Types | Types and models for ephemeral delta. | ✅ |
| `tail_injector.py` | Core | Tail-of-turn injection: `append_block_to_last_human` (text block appended to the final HumanMessage, multimodal parts untouched; shared with `proactive_pack_middleware` and `two_layer_context_middleware`) and `HumanTailDeltaInjector` (XML block of active deltas with `<precedence>` conflict rule). | ✅ |
| `shared_store.py` | Core | Singleton store; `configure_ephemeral_delta_persistence` (refuses db_path flip while buffers hot) + `ensure_ephemeral_deltas_hydrated`. | ✅ |
| `notify.py` | Core | `record_ephemeral_memory_delta` / `clear_ephemeral_deltas_for_session` after durable writes. | ✅ |
