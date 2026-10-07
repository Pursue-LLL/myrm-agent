# Memory Tombstone Server Service Architecture

## 1. Role and Boundaries
This service manages the lifecycle of `MemoryTombstoneCurationService` for `myrm-agent-server`.
It coordinates memory contradiction detection, tombstone recall filtering, and eviction in single-machine user sandboxes.

- **Sandbox Storage**: SQLite ledger stored locally under user's sandbox data directory (`/tmp/myrm_data/myrm_tombstones.db` or configured path).
- **Hard Recall Gate**: Protects prompt assembly pipelines from contradictory outdated memories.
- **Dependency Injection**: Exposes `get_tombstone_curation_service` for FastAPI route dependencies.
