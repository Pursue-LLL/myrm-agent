# db/

## Overview
Database utilities: SQLite migration management plus the unified SQLite hardening
factory (durability / privacy / crash-recovery for every store in the framework).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Database utilities for SQLite migration management. | — |
| `fts5.py` | Core | FTS5 Utilities (query sanitization, integrity check, rebuild from the text the table stores and auto-heal of a damaged index, which declines when the stored rows cannot be read, `fts5_swap_tokenizer` that re-creates a table with another tokenizer in one transaction of its own (called outside a transaction, taking the write lock before it looks at the table again), keeping every row and rowid and, when it fails (a full disk included), leaving the table as it was, and `relevance_from_rank`: an FTS5 bm25 rank turned into a score in [0, 1) that grows with the match strength) | ✅ |
| migration_engine.py | Core | Zero-ops stateful SQLite migration engine (optional `sqlalchemy`; dev/tests). | ✅ |
| sqlite/ | Subpackage | Unified SQLite hardening factory: `SQLiteProfile` presets, sync/async connection hardening with an EIO-safe WAL fallback, and file-level integrity/crash-recovery primitives. See [`sqlite/_ARCH.md`](sqlite/_ARCH.md). | ✅ |
