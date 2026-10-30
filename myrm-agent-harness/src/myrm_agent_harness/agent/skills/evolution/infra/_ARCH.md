# infra/

## Overview
Agent Skills Evolution Infra module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| background_task_manager.py | Core | Background evolution task management with observability and graceful shutdown. | ✅ |
| integration.py | Core | Integration helpers for skill evolution system: screening, manual evolution (`evolve_skill`) and background queue orchestration. A proposal callback may be sync or async. | ✅ |
| queue.py | Core | Defers non-critical evolutions to background queue to avoid blocking main flow. | ✅ |

## Key Dependencies

- `runtime`
- `toolkits`
