# Skill Sync Architecture

## Purpose

Bidirectional skill synchronization enabling collective skill evolution across devices and sandboxes. The framework defines the protocols, the manager, the manifest and a default quality gate; the host application supplies the transport.

## Design Principles

1. **Protocol-first**: `SkillSyncProtocol` and `SkillQualityGateProtocol` are framework-defined interfaces. Business layer provides implementations.
2. **Reuse infrastructure**: Leverages existing `StorageProvider`, `SkillPacker`/`SkillUnpacker`, and `IdleTaskRegistry` — zero new storage primitives.
3. **Incremental sync**: `SkillSyncManifest` (SQLite) tracks per-skill SHA256 hashes and timestamps for efficient delta sync.
4. **Quality gate**: Only skills meeting minimum thresholds (execution count, success rate) get pushed to shared repositories.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Skill sync module exports: protocols, manager, manifest, backends, quality gate. | — |
| types.py | Core | Frozen dataclasses for sync status, push/pull results, and gate verdicts. | ✅ |
| protocols.py | Core | SkillSyncProtocol and SkillQualityGateProtocol framework interfaces. | ✅ |
| manifest.py | Core | SkillSyncManifest SQLite persistence for per-skill SHA256 hashes and sync timestamps. | ✅ |
| quality_gate.py | Core | ThresholdQualityGate default implementation for push validation. | ✅ |
| manager.py | Core | SkillSyncManager orchestrator: pull-first full_sync, push with quality gate. | ✅ |
| idle_integration.py | Core | IdleWorker bridge registering skill_sync periodic task. | ✅ |

## Component Map

```
sync/
├── __init__.py          # Module exports
├── _ARCH.md             # This file
├── types.py             # Data structures (frozen dataclasses)
├── protocols.py         # SkillSyncProtocol + SkillQualityGateProtocol
├── manifest.py          # SkillSyncManifest (SQLite state persistence)
├── quality_gate.py      # ThresholdQualityGate (default impl)
├── manager.py           # SkillSyncManager (orchestrator)
└── idle_integration.py  # IdleWorker registration bridge
```

## Data Flow

```
Evolution Engine ──▶ register_local_skill() ──▶ Manifest (local_ahead)
                                                      │
IdleWorker ─── skill_sync task ──▶ SkillSyncManager.full_sync()
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                    pull_shared_skills()     push_evolved_skills()
                              │                       │
                              ▼                       ▼
                    SyncBackend.pull_skills() QualityGate.evaluate()
                              │                       │
                              ▼                       ▼
                    Unpack + write local     SkillPacker.package_files()
                                                      │
                                                      ▼
                                            SyncBackend.push_skills()
                                                      │
                                                      ▼
                                            Manifest.mark_pushed()
```

## Transport and Quality Gate

`SkillSyncManager` takes a `SkillSyncProtocol` backend from the host: the framework ships no network or
file-system backend. `ThresholdQualityGate` is the default push gate; a host passes its own
`SkillQualityGateProtocol` to replace it.

## Conflict Resolution

The current implementation uses a **pull-first** strategy (`full_sync()` pulls before pushing),
which effectively avoids conflicts by ensuring remote changes are applied before local pushes.

`SkillSyncProtocol.resolve_conflict()` is part of the protocol; `SkillSyncManager` never calls it.

Defined strategies:
- `REMOTE_WINS`: Accept remote (safe for pull-from-marketplace)
- `LOCAL_WINS`: Keep local (safe for push-back)
- `NEWER_WINS`: Reserved, currently falls back to `SKIP`
- `SKIP`: Leave unresolved, local version kept

## Integration Points

- **Evolution Engine**: Calls `manager.register_local_skill()` after skill creation/update
- **IdleWorker**: Periodically triggers `full_sync()` via `skill_sync` task type
- **Server API**: Exposes sync status + manual trigger endpoints
- **Frontend**: Displays sync status indicator + manual sync button
