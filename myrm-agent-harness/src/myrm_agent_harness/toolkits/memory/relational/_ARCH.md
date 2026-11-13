# relational/

## Overview
Relational Store — abstract interface and SQLite implementation.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Relational Store — abstract interface and SQLite implementation. | — |
| _converters.py | Internal | Row-to-model converters for SQLiteRelationalStore; a rule's chat links (`source_chat_id`, `source_chat_ids`) come back from its metadata column as typed fields. | ✅ |
| _exact_fact_store.py | Internal | Zero-loss SQLite storage and FTS5 inverted search handler for exact facts (UUIDs, SHAs, SemVer, config keys). Search is limited in SQL to the caller's primary namespaces (the vector search's visibility predicate) and ranks a memory by its longest matched identifier; a hit only locates the candidate, the caller replaces it with the stored memory. | ✅ |
| _pending_mixin.py | Internal | Pending-record (approval queue) operations of `SQLiteRelationalStore`: submit, resolve, list, count, and delete or count by source chat. A proposal built from several chats records them in its payload and flags the row (`built_from_chats`, partially indexed), so finding the rows of one chat is an indexed lookup, never a scan of the payloads. | ✅ |
| _profile_mixin.py | Internal | Profile operations of `SQLiteRelationalStore`: namespace-scoped get, snapshot with a revision hash, upsert, delete, list and count; an entry may name the chat it was written from (`source_chat_id`), every write replaces that link, and `delete_profiles_by_source_chat_id` / `count_profiles_by_source_chat_id` serve the chat purge and its preview; the maintenance code's `_system.` bookkeeping rows are never listed or counted. | ✅ |
| _rule_mixin.py | Internal | Procedural-rule operations of `SQLiteRelationalStore`: create, get, search, list, count, update and delete, tool-scoped fields included; the chat links of a rule are stored in its metadata column. Rules come out newest first (`created_at DESC, id DESC`), and `create_rule` keeps the creation time a rule carries, in UTC, so an approved proposal keeps its place in line. | ✅ |
| _schema.py | Internal | Table DDL, legacy scope-column migration (including the `built_from_chats` flag of the approval queue and the `source_chat_id` column of profiles) and index creation for `SQLiteRelationalStore`; drops a leftover `priority` column of the rule table (forward-only: a build that reads that column cannot open the database afterwards); reports FTS5 support. | ✅ |
| _store_host.py | Internal | Type-checking-only host contract (connection, error and scope helpers) the three operation mixins rely on; `object` at runtime. | ✅ |
| base.py | Core | Relational store abstraction layer. Defines a backend-agnostic relational storage interface | ✅ |
| exceptions.py | Core | Relational store exceptions including CorruptedMemoryIndexError fail-fast barrier. | ✅ |
| sqlite_store.py | Core | Lightweight relational store backed by aiosqlite with quick_check fail-fast (a failure counts only when a fresh connection reproduces it, since a long-lived connection's cached FTS5 structure goes stale while another connection commits) & poison reset. Owns the connection (one whose setup failed, or that reads as corrupted, is closed and dropped, so the next call opens a fresh one and retries the setup), integrity checks, exact-fact search and lifecycle (the index writes of concurrent callers are serialized, so one memory's rows are always replaced as a unit); the profile, rule and pending operations come from the three mixins. | ✅ |
