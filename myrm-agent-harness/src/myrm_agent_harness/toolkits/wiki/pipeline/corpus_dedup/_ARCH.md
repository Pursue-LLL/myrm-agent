# corpus_dedup/

Raw corpus deduplication governance: fingerprint scan, SQLite persistence, user disposition, and compile eligibility filtering.

## Overview

Three-tier duplicate detection (exact SHA256, normalized hash, simhash near-match) with four dispositions (trash, exclude, dismiss, defer). Trashed files move to `{vault_base}/.corpus_trash/`. Excluded/trashed paths are filtered from compile queue, compiler input, and stale detection. Exact/normalized open groups soft-block compile via server REST. Restore re-enqueues raw files for compile; body snippets support side-by-side review in Settings.

Two guarantees sit on top of the scan:

- **A scan swaps its groups in one transaction** (`replace_scan_groups`). A scan that fails or overlaps another never leaves a half-written or duplicated group set; the scan's start instant is stored in the same transaction as its coverage (`scan_coverage_ns`).
- **Compile hold ("scan first, compile after")**. A connector records each freshly written raw file in the `compile_holds` ledger instead of queueing it. A held file is released to the compile queue once a scan that began after the hold has finished and the file is not a member of an open exact/normalized group; a user disposition (trash/exclude/dismiss/defer) re-runs the release, so the survivor of a resolved group compiles with no manual step. Release is at-least-once (enqueue first, then compare-and-delete the ledger row), and the compile pipeline's own change detection absorbs a repeat.

## File Index

| File | Role | Description | I/O/P |
| --- | --- | --- | --- |
| `__init__.py` | Package | Public exports for scanner, governor, eligibility, store, types, snippets | ✅ |
| `path_utils.py` | SSOT | `normalize_raw_relative_path` — raw-dir-relative path keys | ✅ |
| `types.py` | Types | DedupTier, DispositionAction, DuplicateGroup, PlannedGroup (a group before it is stored), HeldFile, FileEnqueuer (what a release hands files to), DuplicateMemberSnippet, ScanResult, DedupStats, VaultHygieneSnapshot | ✅ |
| `fingerprint.py` | Core | Exact/normalized/simhash fingerprint builders | ✅ |
| `fingerprint_cache.py` | Core | `FingerprintCache` — whole-corpus load, batched upsert and prune of the `file_fingerprints` table | ✅ |
| `compile_holds.py` | Core | `CompileHoldLedger` — durable `compile_holds` table (hold, list, compare-and-delete drop, newer-than query) | ✅ |
| `store.py` | Core | SQLite `.raw_dedup.db` — groups (atomic `replace_scan_groups`), excludes, trash, scan progress and coverage instant, deferred member sets, hygiene listings; owns the fingerprint cache and hold ledger | ✅ |
| `scanner.py` | Core | `CorpusDedupScanner` — incremental scan via fingerprint cache (one cache read, batched writes); plans groups in memory, then swaps them in; deferred cluster matching on regroup | ✅ |
| `governor.py` | Core | `CorpusDedupGovernor` — trash/exclude/dismiss/defer (each followed by a hold release when a compiler is given) · restore with compile enqueue · undo excluded raw · `hold_for_compile` / `release_held` / `release_unguarded` | ✅ |
| `eligibility.py` | Core | `CorpusEligibilityFilter` — blocked-path filter for compile/queue/stale | ✅ |
| `snippets.py` | Core | `build_group_body_snippets` — capped body previews for duplicate review | ✅ |

## Key Dependencies

- `core.structure` (vault paths, raw listing)
- `core.claims_contract` (content hashing)
- `pipeline.raw_gate.evidence_removal` (re-anchor after trash)
- `pipeline.cognitive_map` (restore audit log entries)
- `memory._internal.hash_utils` (normalized text hash)

## Server Integration

Product layer bridges via `app/services/wiki/dedup_runner.py` — REST `/wiki/dedup/*` (POST scan → 202 + background task, GET progress, GET group snippets), cron `__wiki_dedup__`, non-blocking post-import and post-source-sync scan hooks. Scans of one vault run one at a time there; the post-source-sync scan is not skipped while a compile is running (the files it vets are held back from that compile). `app/services/wiki/source_sync/deferred_enqueue.py` is the connector-facing adapter over the hold ledger.
