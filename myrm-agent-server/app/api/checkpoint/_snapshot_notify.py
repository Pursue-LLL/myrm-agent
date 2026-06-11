"""Snapshot restore notification helpers.

Notifies both the Agent (via restore_inbox) and the Frontend (via SSE)
when a file snapshot is successfully restored.

[POS] app/api/checkpoint/_snapshot_notify.py
[INPUT] snapshot_id: str, files_restored: int, files: list[str] | None
[OUTPUT] Side-effects: push_restore_notification → Agent inbox; AppEvent → SSE bus
"""

from __future__ import annotations


def notify_agent_of_restore(snapshot_id: str, files_restored: int, files: list[str] | None) -> None:
    """Push a restore notification so the Agent learns about the rollback on its next turn."""
    from myrm_agent_harness.agent.file_snapshot.restore_inbox import push_restore_notification

    push_restore_notification(
        snapshot_id=snapshot_id,
        files_restored=files_restored,
        restored_files=files,
    )


def emit_restore_event(snapshot_id: str, files_restored: int) -> None:
    """Emit an SSE event so the frontend can show a toast to the user."""
    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        get_event_bus().publish(
            AppEvent(
                event_type=AppEventType.SYSTEM_NOTIFICATION,
                data={
                    "title": "快照恢复",
                    "message": f"已恢复 {files_restored} 个文件到快照 {snapshot_id[:8]}",
                    "meta_data": {
                        "type": "snapshot_restored",
                        "snapshot_id": snapshot_id,
                        "files_restored": files_restored,
                    },
                },
            )
        )
    except Exception:
        pass
