# ephemeral/

## Overview

Subagent memory isolation over a parent `MemoryManager`: a read-only view whose reads delegate to the parent and whose writes raise `PermissionError`. Memory tools are bound to the parent manager and no isolation policy can redirect them, so every `MemoryIsolationPolicy` maps to this one view. Every override keeps the base class signature, and every public `MemoryManager` member is classified (delegated read or denied write) by `tests/toolkits/memory/test_read_only_view_surface.py`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Exports `ReadOnlyMemoryView`. | ✅ |
| `denied_writes.py` | Core | `DeniedMemoryWrites` mixin: every mutating `MemoryManager` method raises `PermissionError` with the base signature. | ✅ |
| `read_only_view.py` | Core | `ReadOnlyMemoryView`: reads delegate to the parent, identity comes from the parent's public accessors, writes come from `DeniedMemoryWrites`. | ✅ |
