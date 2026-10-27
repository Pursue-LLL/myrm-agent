# orchestration/

## Overview

Control-plane LLM signals. **Not Action Tools** — excluded from `_TOOL_LAYERS`, action-tool counts, and default GeneralAgent Turn1 bind.

PTC runtime tools (`spawn_subagent`, `notify`) live in [../dynamic_workflow/_ARCH.md](../dynamic_workflow/_ARCH.md), not here.

| Bucket | Path | Count | Role |
|--------|------|-------|------|
| Orchestration signals | `signals/` | 4 | JSON schemas; orchestrator intercepts tool_calls |
| Inbound steering | `steering.py` | 1 | Bounded quoted-reply queue; boundary injection envelope; never Turn1-bound |

Action Tools SSOT: [../tool_management/_ARCH.md](../tool_management/_ARCH.md)

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Core | Public re-export: `ORCHESTRATION_SIGNAL_NAMES` | ✅ |
| steering.py | Core | `SteeringQueue` inbound queue; `build_steering_context_block` envelope; `drain_into_token` live-Mechanism adapter; snapshot persistence | ✅ |

## Submodule Index

| Path | Description |
|------|-------------|
| `signals/` | Orchestration signal schemas · [signals/_ARCH.md](signals/_ARCH.md) |
