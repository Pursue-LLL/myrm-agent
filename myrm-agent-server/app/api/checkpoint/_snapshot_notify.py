"""Snapshot restore notification helper.

Notifies the Agent (via restore_inbox) when a file snapshot is restored.

[POS] app/api/checkpoint/_snapshot_notify.py
[INPUT] snapshot_id: str, files_restored: int, files: list[str] | None
[OUTPUT] Side-effect: push_restore_notification → Agent inbox
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
