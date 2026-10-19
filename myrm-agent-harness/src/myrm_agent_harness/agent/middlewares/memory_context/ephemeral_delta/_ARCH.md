# ephemeral_delta/

## Overview

Prompt-cache-preserving ephemeral delta memory. Keeps short-lived facts a run discovers in a
per-session registry and mounts them at the human message tail, so the cached prompt prefix is
never rewritten.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the registry, injector and models. | — |
| models.py | Core | Delta, entry and mount-point models. | — |
| registry.py | Core | In-memory session delta registry with conflict reconciliation. | — |
| tail_injector.py | Core | Zero-cache-break message pipeline injector that mounts deltas to the human tail. | — |

## Key Dependencies

- `pydantic` (models)
- message pipeline of the bound agent (mount point)

## Key Design Decisions

- **Tail-only mounting**: deltas are appended at the human message tail, because inserting them
  earlier would invalidate the cached prefix and defeat the point.
- **Conflicts reconcile in the registry**: two deltas claiming the same key are resolved before
  the injector sees them, so the prompt never carries contradictory lines.
- **Session scoped**: the registry is per session, so one run's ephemeral facts cannot leak into
  another's prompt.
