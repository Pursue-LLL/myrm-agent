# ephemeral/

## Overview

Subagent memory isolation strategies over a parent `MemoryManager`: a dict-backed manager whose writes never reach the persistent stores, and a read-only view whose writes raise `PermissionError`. Every override keeps the base class signature.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Exports `EphemeralMemoryManager` and `ReadOnlyMemoryView`. | ✅ |
| `dict_backed.py` | Core | `EphemeralMemoryManager`: reads span the parent and the local dict, writes stay in the dict. | ✅ |
| `read_only_view.py` | Core | `ReadOnlyMemoryView`: reads delegate to the parent, every write raises `PermissionError`. | ✅ |
