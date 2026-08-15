"""Memory operations submodule.

Organized memory operation endpoints by functionality.

[INPUT]
- Memory API requests routed from the memory router into domain subpackages.

[OUTPUT]
- Aggregate facade re-exporting every memory operation subpackage:
  command_center, crud, guardian, pending, reindex, shared_context.

[POS]
Server business layer (Memory API). Single import facade for memory operation
endpoint groups, keeping the memory router thin and each operation domain
self-contained.
"""

from app.api.memory.operations import (
    command_center,
    crud,
    guardian,
    pending,
    reindex,
)
from app.api.memory.operations.shared_context import (
    shared_context_history,
    shared_context_migration,
    shared_contexts,
)

__all__ = [
    "command_center",
    "crud",
    "guardian",
    "pending",
    "reindex",
    "shared_contexts",
    "shared_context_history",
    "shared_context_migration",
]
