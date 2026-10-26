# import_export/

## Overview

Bulk export and import of memories for `MemoryManager`: the store-facing mixin and the stateless rendering it uses. External code reaches the mixin through `memory._manager` only.

## Module Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Exposes `MemoryManagerImportExportMixin` to the manager package | ✅ |
| `mixin.py` | Mixin | `export_all` walks every type to its last page through `iter_pages_by_type` and raises on a store failure, so a backup or export never passes off a truncated result as complete; `export_markdown` serializes only the requested types; `export_rules_safe` reads only the procedural type; `import_memories` recomputes embeddings and routes each type through the writer | ✅ |
| `markdown_render.py` | Internal | Stateless rendering: Markdown files with type-specific YAML frontmatter, filesystem-safe names, home-directory path anonymization and the personal fields a shared rule must not carry | ✅ |
