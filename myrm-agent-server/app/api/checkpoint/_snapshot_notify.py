"""Snapshot restore notification helper.

Notifies the Agent (via restore_inbox) when a file snapshot is restored.

[INPUT]
- myrm_agent_harness.agent.file_snapshot.restore_inbox::push_restore_notification (POS: File restore notification inbox — bridges server restore API and Agent context.)

[OUTPUT]
- notify_agent_of_restore: pushes the snapshot id, the restored files and the external effects into the Agent's restore inbox

[POS]
Restore-notification step of the checkpoint API: after a file snapshot is restored it tells the Agent about the rollback, so the
Agent sees the change on its next turn.
"""

from __future__ import annotations


def notify_agent_of_restore(
    snapshot_id: str,
    files_restored: int,
    files: list[str] | None,
    external_effects: tuple[str, ...] | None = None,
) -> None:
    """Push a restore notification so the Agent learns about the rollback on its next turn."""
    from myrm_agent_harness.agent.file_snapshot.restore_inbox import push_restore_notification

    push_restore_notification(
        snapshot_id=snapshot_id,
        files_restored=files_restored,
        restored_files=files,
        external_effects=external_effects,
    )
