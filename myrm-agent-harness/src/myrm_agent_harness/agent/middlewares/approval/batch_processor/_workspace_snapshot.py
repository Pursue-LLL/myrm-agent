"""[INPUT]
- myrm_agent_harness.toolkits.code_execution.security.workspace_snapshot::create_workspace_snapshot (POS: Harness core execution security: workspace safety net and undo capability.)

[OUTPUT]
- pre_destructive_snapshot_id: snapshot the working directory and return its id, or None when no snapshot could be taken

[POS]
A destructive command waits for the user's approval with a rollback point; the decision loop and the YOLO branch both take it through this helper.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.code_execution.security import workspace_snapshot


def pre_destructive_snapshot_id() -> str | None:
    """Snapshot the working directory; None when it is not a git workspace or the snapshot failed."""
    return workspace_snapshot.create_workspace_snapshot(Path.cwd()).snapshot_id
