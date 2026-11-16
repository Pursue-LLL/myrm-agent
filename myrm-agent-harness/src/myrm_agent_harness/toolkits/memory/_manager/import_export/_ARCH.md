# import_export/

## Overview

Bulk export and import of memories for `MemoryManager`: the store-facing mixin and the stateless rendering it uses. External code reaches the mixin through `memory._manager` only.

## Module Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Exposes `MemoryManagerImportExportMixin` to the manager package | ✅ |
| `mixin.py` | Mixin | `export_all` walks every type to its last page through `iter_pages_by_type` and raises on a store failure, so a backup or export never passes off a truncated result as complete; `export_markdown` serializes only the requested types; `export_rules_safe` reads only the procedural type; `import_memories` recomputes embeddings and routes each type through the writer; with `skip_duplicates=True` the rules the manager already holds (disabled and archived ones count) and the entries that repeat an earlier one are left out before the writer runs, because the writer never deduplicates a rule and a repeated import would put a newer copy of a stale rule ahead of the preference the user stated since; `skip_duplicates=False` bypasses that and makes the writer bypass deduplication (`store_batch(_skip_dedup=True)`), so a replace restore lands every entry; importing reopens the chats the imported memories derive from, because the user brings them back on purpose | ✅ |
| `rule_dedup.py` | Internal | Stateless half of the rule import's deduplication: `rule_identity` (trigger and action, each trimmed, with spacing collapsed and letter case ignored, plus the tool the rule is scoped to) and `without_known_rules` (the imported rules minus the held ones and the repeats within the import, the first of each kept); `mixin.py` reads the stored rules it compares against | ✅ |
| `markdown_render.py` | Internal | Stateless rendering: Markdown files with type-specific YAML frontmatter, filesystem-safe names, home-directory path anonymization and the personal fields a shared rule must not carry | ✅ |
