# services/runs/

## Overview

Run execution lifecycle, attempt telemetry, and multi-surface projection domain services.
Provides state aggregation for execution units across Chat, Runtime Console, Deliverables, and Audit trails.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `projection/` | Subpackage | Pure functional multi-surface run state projection and Attempt telemetry service | [projection/_ARCH.md](projection/_ARCH.md) |

## Dependencies

- `projection/` → `pydantic`, `uuid`, `time`, `logging`
