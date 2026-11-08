# profile_notes/

## Overview
Dual-Layer Profile & Working Notes Memory Budget & Garbage Purge Guard: deterministic intake noise filtering (task progress, ephemeral numbers, error traces), dual-layer routing (USER <= 1375c, MEMORY <= 2200c), and multi-tier capacity watermark governance.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Harness toolkit memory subpackage providing dual-layer memory organization (USER <= 1375c, MEMORY <= 2200c) with deterministic garbage filtering. | ✅ |
| `garbage_filter.py` | Core | Intake gatekeeper implementing the memory guidelines, preventing task progress, ephemeral issue numbers. | ✅ |
| `intake_gate.py` | Core | Intake gatekeeper and prompt formatter for Dual-Layer Profile & Working Notes. | ✅ |
| `types.py` | Types | Foundational types for DualLayerProfileMemoryBudgetAndGarbagePurgeGuard, enforcing memory purity, strict capacity budgets. | ✅ |
| `watermark_governor.py` | Core | Capacity governor enforcing the memory character limits (USER <= 1375, MEMORY <= 2200). | ✅ |

## Key Dependencies

- None (self-contained within the package and the standard library)
