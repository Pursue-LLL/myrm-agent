# services/runs/projection/

## Overview

Pure functional multi-surface run state projection and telemetry service.
Implements MateClaw parity (`UI = Project(RunState, Events)`), managing attempt level watermarks, fault traces, token throughput, and monotonic event aggregation for Chat, Runtime Console, Deliverables, and Audit views.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Module exports for projection contracts and service singleton | ✅ |
| `projection_types.py` | Schema | Pydantic data contracts for snapshot, attempt records, deliverables, and audit entries | ✅ |
| `run_projection_service.py` | Service | Singleton managing run snapshots, monotonic events, and attempt transition watermarks | ✅ |

## Dependencies

- `projection_types.py` → `pydantic`, `typing`
- `run_projection_service.py` → `projection_types.py`, `time`, `uuid`, `logging`
