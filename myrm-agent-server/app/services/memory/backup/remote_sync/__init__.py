"""Scheduled remote memory backup: when it is due, how every outcome is recorded, when the user is told.

[INPUT]
- app.services.memory.backup.remote_sync.job::sync_tick (POS: one tick of the schedule)
- app.services.memory.backup.remote_sync.state::RemoteSyncStore (POS: persisted outcome and instance tag)

[OUTPUT]
- sync_tick: the scheduler entry point
- record_manual_success: a manual backup ends a failure streak
- RemoteSyncState / RemoteSyncStore / default_store: what the status endpoint and the tick read and write
- ALERT_COMPONENT: ``component`` of the HEALTH_ALERT event

[POS]
Off by default; when the user turns auto-sync on, a backup runs at the interval they chose, a restart never repeats a
backup that is not due, and the user is told once when backups keep failing. See _ARCH.md.
"""

from app.services.memory.backup.remote_sync.job import ALERT_COMPONENT, record_manual_success, sync_tick
from app.services.memory.backup.remote_sync.state import RemoteSyncState, RemoteSyncStore, default_store

__all__ = [
    "ALERT_COMPONENT",
    "RemoteSyncState",
    "RemoteSyncStore",
    "default_store",
    "record_manual_success",
    "sync_tick",
]
