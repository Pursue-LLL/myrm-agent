# services/models/overrides/

## Overview

User-defined model context window and pricing override registry.
Implements Hermes Agent v0.21.0 model_overrides parity, decoupling custom context limits and token economics from official release cycles.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Module exports for types, registry, and calculation utilities | ✅ |
| `model_overrides_types.py` | Schema | Pydantic contracts for overrides, 2026 preloaded SKUs, and BYOK cost calculation | ✅ |
| `model_overrides_registry.py` | Registry | Singleton store persisting overrides to disk and computing real-time effective pricing | ✅ |

## Dependencies

- `pydantic`
- `pathlib`, `json`, `logging`
