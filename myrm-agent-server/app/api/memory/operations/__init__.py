"""Memory operations submodule.

Organized memory operation endpoints by functionality.

[INPUT]
- Memory API requests routed from the memory router into domain subpackages.

[OUTPUT]
- Aggregate facade re-exporting the operation modules archive_restore, backup, backup_remote, cognitive_clock_console,
  command_center, command_center_consolidation, command_center_diagnostics, conflicts, crud, domain_mesh,
  evidence_playback, external_transcripts, guardian, head_probe, import_rollback_preview, memory_graph, pending,
  radar, reindex, working_state, plus shared_context_health, shared_context_history and shared_contexts from the
  shared_context subpackage.

[POS]
Server business layer (Memory API). Single import facade for memory operation
endpoint groups, keeping the memory router thin and each operation domain
self-contained.
"""

from app.api.memory.operations import (
    archive_restore,
    backup,
    backup_remote,
    cognitive_clock_console,
    command_center,
    command_center_consolidation,
    command_center_diagnostics,
    conflicts,
    crud,
    domain_mesh,
    evidence_playback,
    external_transcripts,
    guardian,
    head_probe,
    import_rollback_preview,
    memory_graph,
    pending,
    radar,
    reindex,
    working_state,
)
from app.api.memory.operations.shared_context import (
    shared_context_health,
    shared_context_history,
    shared_contexts,
)

__all__ = [
    "archive_restore",
    "backup",
    "backup_remote",
    "cognitive_clock_console",
    "command_center",
    "command_center_consolidation",
    "command_center_diagnostics",
    "conflicts",
    "crud",
    "domain_mesh",
    "evidence_playback",
    "external_transcripts",
    "guardian",
    "head_probe",
    "import_rollback_preview",
    "memory_graph",
    "pending",
    "radar",
    "reindex",
    "working_state",
    "shared_context_health",
    "shared_context_history",
    "shared_contexts",
]
