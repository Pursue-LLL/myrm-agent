"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- _remote_backup_scheduler_task, _remote_backup_auto_sync_job, start_remote_backup_scheduler, stop_remote_backup_scheduler

[POS]
Lifecycle schedulers: remote memory backup auto-sync.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.infra.background_task import spawn_observed_task

from .common import logger

if TYPE_CHECKING:
    pass

_remote_backup_scheduler_task: asyncio.Task[None] | None = None


async def _remote_backup_auto_sync_job() -> None:
    """Hourly check of the scheduled remote memory backup; starts one only when the user's interval has passed."""
    try:
        from datetime import UTC, datetime

        from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager
        from app.services.config.service import config_service
        from app.services.memory.backup.remote_sync import default_store, sync_tick

        record = await config_service.get("backupSync")
        await sync_tick(
            record.value if record else None,
            store=default_store(),
            manager_factory=create_guardian_memory_manager,
            now=datetime.now(UTC),
            # A stored row whose key is gone is not the same as settings that were never saved.
            settings_unreadable=record is not None and record.unreadable,
        )
    except Exception as exc:
        logger.warning("Remote backup auto-sync job failed: %s", exc)


async def start_remote_backup_scheduler() -> None:
    """Start the hourly check of the scheduled remote memory backup.

    Whether a backup is due comes from the recorded last success and the user's ``backupSync.syncInterval``, so a
    restart never repeats one. The job does nothing unless ``backupSync.enabled`` and ``backupSync.autoSync`` are true.
    """
    global _remote_backup_scheduler_task

    try:
        from datetime import UTC, datetime, timedelta

        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        from app.services.memory.backup.remote_sync.schedule import TICK_MINUTES

        async def run_scheduler() -> None:
            async with AsyncScheduler() as scheduler:
                # First check a few minutes after boot (not at once) so a backup due from a closed period does
                # not compete with startup.
                await scheduler.add_schedule(
                    _remote_backup_auto_sync_job,
                    IntervalTrigger(minutes=TICK_MINUTES, start_time=datetime.now(UTC) + timedelta(minutes=5)),
                    id="remote_backup_auto_sync",
                )
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Remote backup auto-sync scheduler started (checks every %d min)", TICK_MINUTES)
                await asyncio.Event().wait()

        _remote_backup_scheduler_task = spawn_observed_task(run_scheduler(), name="remote_backup_auto_sync")

    except Exception as exc:
        logger.error("Failed to start remote backup scheduler: %s", exc)


async def stop_remote_backup_scheduler() -> None:
    """Stop the remote backup auto-sync scheduler."""
    global _remote_backup_scheduler_task

    if _remote_backup_scheduler_task is None:
        return

    try:
        _remote_backup_scheduler_task.cancel()
        try:
            await _remote_backup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Remote backup scheduler stopped")
    except Exception as e:
        logger.error("[Shutdown] Remote backup scheduler stop failed: %s", e)
    finally:
        _remote_backup_scheduler_task = None
