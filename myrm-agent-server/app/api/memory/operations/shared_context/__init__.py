"""Shared-context API domain: CRUD, health, history, migration + serializers.

[INPUT]
- Shared-context write/read payloads from the memory router.
- SharedContextModel / SharedContextBindingModel / SharedContextWriteProposalModel
  rows (SQLAlchemy async sessions).

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``shared_context``
  subpackage:
  - shared_contexts: ``router`` (prefix ``/shared-contexts``) — list/create/get
    bindings CRUD + event recording
  - shared_context_health: ``router`` (``/shared-contexts/health``) — memory
    health snapshot
  - shared_context_history: ``router`` — history search + proposal creation
  - shared_context_migration: ``router`` — legacy team-memory migration
  - shared_context_serializers: model → item/serialization helpers

[POS]
Server business layer (Memory API). Single shared-context domain: CRUD, health,
history and migration routers share the serializers and are mounted together by
``api.memory.router``, so they stay co-located under one facade.
"""

from app.api.memory.operations.shared_context.shared_context_health import (
    router as health_router,
)
from app.api.memory.operations.shared_context.shared_context_history import (
    router as history_router,
)
from app.api.memory.operations.shared_context.shared_context_migration import (
    router as migration_router,
)
from app.api.memory.operations.shared_context.shared_context_serializers import (
    binding_to_item,
    context_to_item,
    proposal_to_item,
)
from app.api.memory.operations.shared_context.shared_contexts import router

__all__ = [
    "binding_to_item",
    "context_to_item",
    "health_router",
    "history_router",
    "migration_router",
    "proposal_to_item",
    "router",
]
