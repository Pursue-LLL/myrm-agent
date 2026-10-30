# db/

## Overview
Agent Skills Evolution Db module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| store.py | Core | SQLite persistence for skill evolution system — lifecycle, CRUD, eval_cases persistence. Content length guard: `save_skill` / `save_skills_batch` reject records whose content exceeds `MAX_SKILL_CONTENT_CHARS` (ValueError) so oversized skills never reach storage. It stores no per-skill execution counters (usage and success rate live in the Curator's `.stats.json`); counter columns already present in an existing database are left unused. Inherits evolution tracking from `_store_evolution_tracking` and dependency graph persistence from `_store_dependencies`. | ✅ |
| store_queries.py | Core | Complex query methods for SkillStore. | ✅ |
| _store_schema.py | Internal | `SCHEMA_DDL` (the skills, rejections and constraints tables) and `migrate_existing_db`: idempotent upgrades run on every open — add the `skills` columns a database lacks (`verification_steps`, `eval_cases`, `evolution_locked`, `environment`), delete the constraint notes that engine and screener prefixes mark as automatic (the constraints table keeps user rejection reasons only), and re-type `optimize_description` records as `fix`. | ✅ |
| _store_retry.py | Internal | `db_retry`: decorator retrying a synchronous store operation on any `sqlite3.DatabaseError` (a locked database included, constraint violations too) with exponential backoff — 5 attempts, 1.5 s of pauses in total with the defaults; `InterfaceError` and non-sqlite exceptions propagate at once. | ✅ |
| _store_evolution_tracking.py | Internal | Evolution tracking persistence mixin — rejections, constraints. | ✅ |
| _store_dependencies.py | Internal | Persistent skill dependency tracking mixin — resolves frontmatter `dependencies`/body tool markers at write time into `skill_dependencies` edges, exposes `get_dependents` / `get_dependents_map` / `get_skill_dependencies` for impact analysis. | ✅ |
