"""Memory operations submodule.

Organized memory operation endpoints by functionality.

[INPUT]
- Memory API requests routed from the memory router into domain subpackages.

[OUTPUT]
- Aggregate facade re-exporting every memory operation subpackage:
  archive_restore, backup, backup_remote, command_center, crud, guardian,
  pending, reindex, working_state, shared_context.

[POS]
Server business layer (Memory API). Single import facade for memory operation
endpoint groups, keeping the memory router thin and each operation domain
self-contained.
"""

from app.api.memory.operations import (
    archive_restore,
    backup,
    backup_remote,
    command_center,
    command_center_consolidation,
    command_center_diagnostics,
    crud,
    external_transcripts,
    guardian,
    pending,
    reindex,
    working_state,
)
from app.api.memory.operations.shared_context import (
    shared_context_health,
    shared_context_history,
    shared_context_migration,
    shared_contexts,
)

__all__ = [
    "archive_restore",
    "backup",
    "backup_remote",
    "command_center",
    "command_center_consolidation",
    "command_center_diagnostics",
    "crud",
    "external_transcripts",
    "guardian",
    "pending",
    "reindex",
    "working_state",
    "shared_context_health",
    "shared_context_history",
    "shared_context_migration",
    "shared_contexts",
]
