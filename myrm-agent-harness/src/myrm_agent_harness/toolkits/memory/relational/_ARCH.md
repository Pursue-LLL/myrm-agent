# relational/

## Overview
Relational Store — abstract interface and SQLite implementation.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Relational Store — abstract interface and SQLite implementation. | — |
| _converters.py | Internal | Row-to-model converters for SQLiteRelationalStore. | ✅ |
| _exact_fact_store.py | Internal | Zero-loss SQLite storage and FTS5 inverted search handler for exact facts (UUIDs, SHAs, SemVer, config keys). Search is limited in SQL to the caller's primary namespaces (the vector search's visibility predicate) and ranks a memory by its longest matched identifier; a hit only locates the candidate, the caller replaces it with the stored memory. | ✅ |
| _pending_mixin.py | Internal | Pending-record (approval queue) operations of `SQLiteRelationalStore`: submit, resolve, list, count, and delete or count by source chat. | ✅ |
| _profile_mixin.py | Internal | Profile operations of `SQLiteRelationalStore`: namespace-scoped get, snapshot with a revision hash, upsert, delete, list and count; the maintenance code's `_system.` bookkeeping rows are never listed or counted. | ✅ |
| _rule_mixin.py | Internal | Procedural-rule operations of `SQLiteRelationalStore`: create, get, search, list, count, update and delete, tool-scoped fields included. | ✅ |
| _schema.py | Internal | Table DDL, legacy scope-column migration and index creation for `SQLiteRelationalStore`; reports FTS5 support. | ✅ |
| _store_host.py | Internal | Type-checking-only host contract (connection, error and scope helpers) the three operation mixins rely on; `object` at runtime. | ✅ |
| base.py | Core | Relational store abstraction layer. Defines a backend-agnostic relational storage interface | ✅ |
| exceptions.py | Core | Relational store exceptions including CorruptedMemoryIndexError fail-fast barrier. | ✅ |
| sqlite_store.py | Core | Lightweight relational store backed by aiosqlite with quick_check fail-fast (a failure counts only when a fresh connection reproduces it, since a long-lived connection's cached FTS5 structure goes stale while another connection commits) & poison reset. Owns the connection, integrity checks, exact-fact search and lifecycle; the profile, rule and pending operations come from the three mixins. | ✅ |
