"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- _db_maintenance_scheduler, _db_maintenance_scheduler_task, _db_maintenance_job, _incognito_cleanup_job, _checkpoint_history_prune_job, _instance_auto_backup_job, start_db_maintenance_scheduler, stop_db_maintenance_scheduler

[POS]
Lifecycle schedulers: database maintenance, incognito purge, checkpoint prune and instance backup jobs.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.infra.background_task import spawn_observed_task

from .common import logger

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler

_db_maintenance_scheduler: AsyncScheduler | None = None


_db_maintenance_scheduler_task: asyncio.Task[None] | None = None


async def _db_maintenance_job() -> None:
    """Periodic database maintenance (every 6h).

    Tasks:
    1. SQLite WAL checkpoint — prevents WAL file unbounded growth
    2. Database backup — disaster recovery snapshot
    3. Memory import review cleanup — remove rollback-expired import sessions
    4. Async task queue cleanup — prune terminal tasks older than 30 days (tasks.db)
    5. Chat trash auto-purge — permanently delete chats trashed > 30 days
    6. Kanban data GC — clean old events/runs/workspaces for terminal tasks
    7. Artifact share registry GC — remove expired share records (TTL + retention)
    8. Channel data plane GC — prune channel messages older than 30 days
    9. Browser session GC — remove expired saved login sessions (global vault + every agent vault)
    """
    # SQLite WAL checkpoint
    try:
        from sqlalchemy import text

        from app.platform_utils import session_factory

        async with session_factory() as session:
            result = await session.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            row = result.fetchone()
            if row:
                logger.info(
                    "SQLite WAL checkpoint: busy=%s, log=%s, checkpointed=%s",
                    row[0],
                    row[1],
                    row[2],
                )
            else:
                logger.info("SQLite WAL checkpoint completed")
    except Exception as e:
        logger.warning("SQLite WAL checkpoint failed: %s", e)

    # Database Backup (integrity-verified rotated snapshot)
    try:
        from app.database.operations.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            # Copying, verifying and hashing the image takes seconds on a grown database: keep it off the event loop.
            await asyncio.to_thread(manager.create_backup)
            logger.info("Periodic database backup completed")
    except Exception as e:
        logger.warning("Periodic database backup failed: %s", e)

    # Memory import review cleanup
    try:
        from app.platform_utils import session_factory
        from app.services.memory.imports.import_sessions import MemoryImportSessionService

        async with session_factory() as session:
            deleted = await MemoryImportSessionService(session).cleanup_sessions()
        if deleted > 0:
            logger.info(
                "Memory import review cleanup: %d expired review sessions removed",
                deleted,
            )
    except Exception as e:
        logger.warning("Memory import review cleanup failed: %s", e)

    # Async job queue (image generation tasks.db)
    try:
        from app.lifecycle.task_worker import get_task_store
        from app.tasks.cleanup import cleanup_old_tasks

        deleted_tasks = await cleanup_old_tasks(get_task_store(), days=30)
        if deleted_tasks > 0:
            logger.info("Async task cleanup: %d terminal tasks removed", deleted_tasks)
    except RuntimeError:
        logger.debug("Async task cleanup skipped: task store not initialized")
    except Exception as e:
        logger.warning("Async task cleanup failed: %s", e)

    # Chat trash auto-purge: permanently delete chats trashed past the retention window
    try:
        from app.services.chat.chat_retention import purge_expired_trash

        await purge_expired_trash()
    except Exception as e:
        logger.warning("Chat trash auto-purge failed: %s", e)

    # Kanban data GC: clean old events/runs/workspaces for terminal tasks
    try:
        from app.services.kanban.gc import KanbanGCService

        await KanbanGCService().run_gc()
    except Exception as e:
        logger.warning("Kanban data GC failed: %s", e)

    # Artifact share registry GC: remove DB rows past TTL + retention grace.
    # Keeps registry rows in sync with purge_expired_share_bundles (on-disk).
    try:
        from app.platform_utils import session_factory
        from app.services.artifacts.share.share_registry import purge_expired_shares

        async with session_factory() as session:
            removed = await purge_expired_shares(session)
        if removed > 0:
            logger.info(
                "Artifact share registry GC: %d expired share records removed",
                removed,
            )
    except Exception as e:
        logger.warning("Artifact share registry GC failed: %s", e)

    # Channel data plane GC: prune inbound channel messages older than 30 days
    try:
        from app.database.repositories.channel_message_repo import ChannelMessageRepository
        from app.platform_utils import session_factory

        async with session_factory() as session:
            pruned_count = await ChannelMessageRepository.prune_expired(session, retention_days=30)
            await session.commit()
        if pruned_count > 0:
            logger.info("Channel data plane GC: %d expired messages pruned", pruned_count)
    except Exception as e:
        logger.warning("Channel data plane GC failed: %s", e)

    # Browser session GC: saved login sessions past their TTL are only dropped lazily on read otherwise
    try:
        from app.core.security.browser_vault import cleanup_all_vaults

        removed_sessions = await cleanup_all_vaults()
        if removed_sessions > 0:
            logger.info("Browser session GC: %d expired saved sessions removed", removed_sessions)
    except Exception as e:
        logger.warning("Browser session GC failed: %s", e)


async def _incognito_cleanup_job() -> None:
    """Incognito chat auto-purge: permanently delete idle web incognito chats that have no turn in flight"""
    try:
        from app.services.chat.chat_retention import purge_idle_incognito_chats

        await purge_idle_incognito_chats()
    except Exception as e:
        logger.warning("Incognito chat auto-purge failed: %s", e)


async def _checkpoint_history_prune_job() -> None:
    """Drop superseded checkpoint history and hand the freed space back to the filesystem."""
    from app.services.system.checkpoint_history_service import run_checkpoint_history_prune

    await run_checkpoint_history_prune()


async def _instance_auto_backup_job() -> None:
    """Hourly check of the scheduled whole-instance backup; starts one only when it is due."""
    from app.services.instance_archive.auto_backup import run_auto_backup_tick

    await run_auto_backup_tick()


async def start_db_maintenance_scheduler() -> None:
    """Start database maintenance scheduler (every 6 hours)."""
    global _db_maintenance_scheduler, _db_maintenance_scheduler_task

    try:
        from datetime import UTC, datetime, timedelta

        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager."""
            async with AsyncScheduler() as scheduler:
                # First pass a few minutes after boot (not at once): the snapshot, trash purge and GC sweeps would
                # otherwise compete with the first screen's requests for the event loop and SQLite write locks.
                await scheduler.add_schedule(
                    _db_maintenance_job,
                    IntervalTrigger(hours=6, start_time=datetime.now(UTC) + timedelta(minutes=3)),
                    id="db_maintenance",
                )
                await scheduler.add_schedule(
                    _incognito_cleanup_job,
                    IntervalTrigger(minutes=60),
                    id="incognito_cleanup",
                )
                # Delayed so the first pass over a long-grown checkpoint database does not compete with startup;
                # it works in small lock-releasing batches, so conversations keep running meanwhile.
                await scheduler.add_schedule(
                    _checkpoint_history_prune_job,
                    IntervalTrigger(hours=6, start_time=datetime.now(UTC) + timedelta(minutes=10)),
                    id="checkpoint_history_prune",
                )
                # First check a few minutes after boot (not at once) so a backup due from a closed period does
                # not compete with startup; the due-ness itself comes from the recorded last completed backup.
                await scheduler.add_schedule(
                    _instance_auto_backup_job,
                    IntervalTrigger(minutes=60, start_time=datetime.now(UTC) + timedelta(minutes=5)),
                    id="instance_auto_backup",
                )
                global _db_maintenance_scheduler
                _db_maintenance_scheduler = scheduler
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("DB maintenance scheduler started (every 6 hours)")
                await asyncio.Event().wait()

        _db_maintenance_scheduler_task = spawn_observed_task(run_scheduler(), name="db_maintenance")

    except Exception as e:
        logger.error("Failed to start DB maintenance scheduler: %s", e)


async def stop_db_maintenance_scheduler() -> None:
    """Stop the database maintenance scheduler."""
    global _db_maintenance_scheduler, _db_maintenance_scheduler_task

    if _db_maintenance_scheduler_task is None:
        return

    try:
        _db_maintenance_scheduler_task.cancel()
        try:
            await _db_maintenance_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] DB maintenance scheduler stopped")
    except Exception as e:
        logger.error("[Shutdown] DB maintenance scheduler stop failed: %s", e)
    finally:
        _db_maintenance_scheduler = None
        _db_maintenance_scheduler_task = None
