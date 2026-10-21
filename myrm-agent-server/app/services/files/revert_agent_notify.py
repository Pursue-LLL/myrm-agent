"""Notify the Agent after turn-level file revert (WebUI / IM /undo).

[INPUT]
- myrm_agent_harness.agent.file_snapshot.restore_inbox::push_restore_notification (POS: File restore notification inbox)

[OUTPUT]
- notify_agent_of_turn_revert: enqueue restore_inbox notification for the next Agent turn

[POS]
Turn-level file revert Agent notification. Shared by revert HTTP API and channel /undo·/retry.
"""

from __future__ import annotations


def notify_agent_of_turn_revert(
    *,
    session_id: str,
    message_id: str | None,
    reverted_files: list[str],
) -> None:
    """Push restore_inbox notification so the Agent re-reads disk on its next turn."""
    if not reverted_files:
        return

    from myrm_agent_harness.agent.file_snapshot.restore_inbox import push_restore_notification

    snapshot_id = f"turn:{message_id}" if message_id else f"session:{session_id}"
    push_restore_notification(
        snapshot_id=snapshot_id,
        files_restored=len(reverted_files),
        restored_files=reverted_files,
    )
