# health/

## Overview
Business-level health checking implementations. Provides concrete health checkers for Qdrant, SQLite, and Browser resources, with automatic recovery capabilities.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Health checking business layer exports. | ✅ |
| qdrant.py | Core | Qdrant path verifier (Lock management is natively handled by Qdrant Rust engine with Server entrypoint Phantom-Kill). | ✅ |
| sqlite.py | Core | SQLite health checker with PRAGMA quick_check integrity verification and backup-based recovery via SQLiteBackupManager. | ✅ |
| browser.py | Core | Browser pool health checker (orphan automation processes). | ✅ |
| coordinator.py | Core | Business-level health check coordinator that instantiates and runs all checkers. | ✅ |

## Module Dependencies

**Internal Dependencies:**
- `myrm_agent_harness.infra.health` — Framework-level health check abstractions
- `myrm_agent_harness.infra.sqlite_backup` — SQLite hot-backup manager
- `app.config.settings` — Application configuration

**Used By:**
- `run.py` — Startup health check integration
- `app.api.health.router` — Health API endpoints
