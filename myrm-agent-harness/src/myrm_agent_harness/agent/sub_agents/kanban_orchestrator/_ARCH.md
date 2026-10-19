# kanban_orchestrator/

## Overview

Multi-agent kanban orchestration. Computes card dependencies as a DAG, topologically orders
them, and drives card lifecycle through a dispatcher with card-scoped sandboxes and
auto-unblock cascades.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports the DAG engine, dispatcher and models. | — |
| dag_engine.py | Core | DAG dependency calculation and topological analysis across cards. | — |
| dispatcher.py | Core | `KanbanCardLifecycleDispatcher` — drives card transitions, card-scoped sandboxes and auto-unblock cascades. | — |
| types.py | Core | Card, dependency, and lifecycle state models. | — |

## Key Dependencies

- `pydantic` (models)

## Key Design Decisions

- **One DAG per board**: dependency analysis is computed from the board's cards, so a card
  cannot be dispatched before its dependencies are done.
- **Sandboxes are card-scoped**: a card's execution cannot leak into a sibling card's workspace.
- **Unblocking cascades forward only**: finishing a card re-evaluates its dependents once, and a
  dependent that is still blocked stays blocked.
