# db/

## Overview
Agent Skills Evolution Db module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| store.py | Core | SQLite persistence for skill evolution system — lifecycle, CRUD, eval_cases persistence. Content length guard: `save_skill` / `save_skills_batch` reject records whose content exceeds `MAX_SKILL_CONTENT_CHARS` (ValueError) so oversized skills never reach storage. It stores no per-skill execution counters (usage and success rate live in the Curator's `.stats.json`); counter columns already present in an existing database are left unused. Inherits evolution tracking from `_store_evolution_tracking` and dependency graph persistence from `_store_dependencies`. | ✅ |
| store_queries.py | Core | Complex query methods for SkillStore. | ✅ |
| _store_schema.py | Internal | `SCHEMA_DDL` (the skills, rejections and constraints tables) and `migrate_existing_db`: idempotent upgrades run on every open — adds missing `skills` columns, drops the automatic constraint notes older versions wrote (the constraints table keeps user rejection reasons only), and re-types retired `optimize_description` records as `fix`. Schema and migrations live together so a new column is declared and upgraded in one place. | ✅ |
| _store_retry.py | Internal | `db_retry`: decorator retrying a synchronous store operation with exponential backoff on `OperationalError`/`DatabaseError` (e.g. a locked database); programming errors are not retried. | ✅ |
| _store_evolution_tracking.py | Internal | Evolution tracking persistence mixin — rejections, constraints. | ✅ |
| _store_dependencies.py | Internal | Persistent skill dependency tracking mixin — resolves frontmatter `dependencies`/body tool markers at write time into `skill_dependencies` edges, exposes `get_dependents` / `get_dependents_map` / `get_skill_dependencies` for impact analysis. | ✅ |
