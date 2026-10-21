"""Application lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import TYPE_CHECKING

from app.core.infra.background_task import spawn_observed_task

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler


logger = logging.getLogger(__name__)

_context_cleanup_scheduler: AsyncScheduler | None = None

_db_maintenance_scheduler: AsyncScheduler | None = None

_login_session_cleanup_scheduler: AsyncScheduler | None = None

_auth_log_cleanup_scheduler: AsyncScheduler | None = None

_MONITOR_CLEANUP_BATCH_SIZE = 500
_MONITOR_STARTUP_MAX_BATCHES = 4


async def _auth_log_cleanup_job() -> None:
    """Periodic auth audit log cleanup (removes old archived logs)."""

    from app.config.settings import get_settings
    from app.middleware.auth_audit import AUDIT_LOG_FILE, _get_rotator

    try:
        settings = get_settings()
        rotator = _get_rotator()
        archive_dir = AUDIT_LOG_FILE.parent / rotator.config.archive_dir
        rotator.cleanup_old_logs(archive_dir, settings.auth_audit_log_retention_days)
    except Exception as exc:
        logger.warning("Auth log cleanup failed: %s", exc)


async def _context_cleanup_job() -> None:
    """Daily context file cleanup task (module-level for APScheduler serialization)."""
    from myrm_agent_harness.runtime.context.offload import (
        cleanup_orphan_context_files_async,
    )

    access_tracker = None
    try:
        from myrm_agent_harness.runtime.context.file_access_tracker import (
            get_file_access_tracker,
        )

        access_tracker = await get_file_access_tracker()
    except Exception as exc:
        logger.warning("File access tracker unavailable for cleanup, using modification time only: %s", exc)

    try:
        removed_count = await cleanup_orphan_context_files_async(access_tracker=access_tracker)
        logger.info("Context cleanup: removed %d orphan files", removed_count)
    except Exception as e:
        logger.error(f"Context cleanup failed: {e}", exc_info=True)

    try:
        from app.services.agent.context_guard_service import ContextGuardService

        cleaned_spillover = ContextGuardService.sweep_all_workspaces()
        if cleaned_spillover > 0:
            logger.info("Context cleanup: swept %d expired transient spillover files", cleaned_spillover)
    except Exception as e:
        logger.warning(f"ContextGuard transient spillover sweep failed: {e}")


async def start_cron_scheduler() -> None:
    """启动 Cron Scheduler（定时任务调度器）"""
    from app.core.cron.adapters.setup import get_cron_scheduler, get_cron_store

    try:
        cleanup_stats = await get_cron_store().normalize_monitor_configs_batch(
            batch_size=_MONITOR_CLEANUP_BATCH_SIZE,
            max_batches=_MONITOR_STARTUP_MAX_BATCHES,
        )
        if cleanup_stats.normalized_count > 0:
            logger.info(
                "Cron startup cleanup normalized %d legacy monitor_config payloads",
                cleanup_stats.normalized_count,
            )
        if cleanup_stats.continuation_required:
            logger.info(
                "Cron startup monitor_config cleanup has remaining rows; continuation required (scanned=%d, batches=%d)",
                cleanup_stats.scanned_count,
                cleanup_stats.processed_batches,
            )
    except Exception as exc:
        logger.warning("Cron startup monitor_config cleanup failed: %s", exc)

    try:
        from app.services.onboarding.second_brain_preset import (
            reconcile_second_brain_cron_ids,
        )
        from app.services.wiki.source_sync.read_it_later_hygiene import (
            migrate_stale_read_it_later_jobs,
        )

        hygiene = await migrate_stale_read_it_later_jobs()
        if hygiene.migrated_count:
            logger.info(
                "Cron startup migrated %d stale read-it-later job(s)",
                hygiene.migrated_count,
            )
        await reconcile_second_brain_cron_ids(hygiene.id_remaps)
    except Exception as exc:
        logger.warning("Cron startup read-it-later hygiene failed: %s", exc)

    try:
        from app.services.onboarding.second_brain_preset import (
            repair_wiki_delta_job_security,
        )

        await repair_wiki_delta_job_security()
    except Exception as exc:
        logger.warning("Cron startup wiki-delta job repair failed: %s", exc)

    await get_cron_scheduler().start()
    logger.info("Cron scheduler started")


_context_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def start_context_cleanup_scheduler() -> None:
    """Start the context file cleanup scheduler.

    A context file is removed once nothing has read or written it for the harness retention window.

    Scheduled daily at 3:00 AM.
    """
    global _context_cleanup_scheduler, _context_cleanup_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.cron import CronTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager (correct apscheduler lifecycle)."""
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _context_cleanup_job,
                    CronTrigger(hour=3, minute=0),
                    id="context_cleanup",
                )
                # Keep scheduler reference for graceful shutdown
                global _context_cleanup_scheduler
                _context_cleanup_scheduler = scheduler
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Context cleanup scheduler started (daily at 03:00)")
                # Run until cancelled
                await asyncio.Event().wait()

        _context_cleanup_scheduler_task = spawn_observed_task(run_scheduler(), name="context_cleanup")

    except Exception as e:
        logger.error(f"Failed to start context cleanup scheduler: {e}", exc_info=True)


async def stop_context_cleanup_scheduler() -> None:
    """Stop the context cleanup scheduler gracefully."""
    global _context_cleanup_scheduler, _context_cleanup_scheduler_task

    if _context_cleanup_scheduler_task is None:
        return

    try:
        _context_cleanup_scheduler_task.cancel()
        try:
            await _context_cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Context cleanup scheduler stopped")
    except Exception as e:
        logger.error(f"[Shutdown] Context cleanup scheduler stop failed: {e}")
    finally:
        _context_cleanup_scheduler = None
        _context_cleanup_scheduler_task = None


async def start_context_compaction_telemetry_dispatcher() -> None:
    """Start server-side batching dispatcher for context compaction telemetry."""
    from app.services.agent.context_compaction_telemetry import (
        start_context_compaction_telemetry_dispatcher as _start_dispatcher,
    )

    await _start_dispatcher()


async def stop_context_compaction_telemetry_dispatcher() -> None:
    """Stop server-side batching dispatcher for context compaction telemetry."""
    from app.services.agent.context_compaction_telemetry import (
        stop_context_compaction_telemetry_dispatcher as _stop_dispatcher,
    )

    await _stop_dispatcher()


async def start_memory_brief_status_telemetry_dispatcher() -> None:
    """Start server-side batching dispatcher for memory brief status telemetry."""
    from app.services.agent.memory_brief_telemetry import (
        start_memory_brief_status_telemetry_dispatcher as _start_dispatcher,
    )

    await _start_dispatcher()


async def stop_memory_brief_status_telemetry_dispatcher() -> None:
    """Stop server-side batching dispatcher for memory brief status telemetry."""
    from app.services.agent.memory_brief_telemetry import (
        stop_memory_brief_status_telemetry_dispatcher as _stop_dispatcher,
    )

    await _stop_dispatcher()


async def start_memory_guardian_guard_telemetry_dispatcher() -> None:
    """Start server-side batching dispatcher for guardian guard-unavailable telemetry."""
    from app.services.agent.memory_guardian_guard_telemetry import (
        start_memory_guardian_guard_telemetry_dispatcher as _start_dispatcher,
    )

    await _start_dispatcher()


async def stop_memory_guardian_guard_telemetry_dispatcher() -> None:
    """Stop server-side batching dispatcher for guardian guard-unavailable telemetry."""
    from app.services.agent.memory_guardian_guard_telemetry import (
        stop_memory_guardian_guard_telemetry_dispatcher as _stop_dispatcher,
    )

    await _stop_dispatcher()


async def _approval_ttl_job() -> None:
    """Periodic approval TTL job (rejects expired approvals)."""
    try:
        from app.services.approvals.registry import ApprovalRegistry

        rejected_count = await ApprovalRegistry.cleanup_expired_approvals()
        if rejected_count > 0:
            logger.info("Approval TTL cleanup: %d expired approvals rejected", rejected_count)
    except Exception as exc:
        logger.warning("Approval TTL cleanup failed: %s", exc)


_approval_ttl_scheduler_task: asyncio.Task[None] | None = None


async def start_approval_ttl_scheduler() -> None:
    """Start approval TTL auto-downgrade scheduler (every 5 minutes)."""
    global _approval_ttl_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager."""
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _approval_ttl_job,
                    IntervalTrigger(minutes=5),
                    id="approval_ttl_cleanup",
                )
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Approval TTL scheduler started (every 5 min)")
                await asyncio.Event().wait()

        _approval_ttl_scheduler_task = spawn_observed_task(run_scheduler(), name="approval_ttl_cleanup")

    except Exception as exc:
        logger.error("Failed to start approval TTL scheduler: %s", exc)


async def stop_approval_ttl_scheduler() -> None:
    """Stop the approval TTL scheduler."""
    global _approval_ttl_scheduler_task

    if _approval_ttl_scheduler_task is None:
        return

    try:
        _approval_ttl_scheduler_task.cancel()
        try:
            await _approval_ttl_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Approval TTL scheduler stopped")
    except Exception as exc:
        logger.error("[Shutdown] Approval TTL scheduler stop failed: %s", exc)
    finally:
        _approval_ttl_scheduler_task = None


async def _cancellation_token_cleanup_job() -> None:
    """Periodic CancellationToken TTL cleanup (removes leaked tokens older than 1 hour)."""
    try:
        from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry

        removed = CancellationRegistry.cleanup_expired(ttl_seconds=3600)
        if removed > 0:
            logger.info("CancellationToken cleanup: %d expired tokens removed", removed)
    except Exception as exc:
        logger.warning("CancellationToken cleanup failed: %s", exc)


_cancellation_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def start_cancellation_cleanup_scheduler() -> None:
    """Start CancellationToken TTL cleanup scheduler (every 10 minutes)."""
    global _cancellation_cleanup_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager."""
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _cancellation_token_cleanup_job,
                    IntervalTrigger(minutes=10),
                    id="cancellation_token_cleanup",
                )
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("CancellationToken cleanup scheduler started (every 10 min)")
                await asyncio.Event().wait()

        _cancellation_cleanup_scheduler_task = spawn_observed_task(run_scheduler(), name="cancellation_token_cleanup")

    except Exception as exc:
        logger.error("Failed to start CancellationToken cleanup scheduler: %s", exc)


async def stop_cancellation_cleanup_scheduler() -> None:
    """Stop the CancellationToken cleanup scheduler."""
    global _cancellation_cleanup_scheduler_task

    if _cancellation_cleanup_scheduler_task is None:
        return

    try:
        _cancellation_cleanup_scheduler_task.cancel()
        try:
            await _cancellation_cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] CancellationToken cleanup scheduler stopped")
    except Exception as exc:
        logger.error("[Shutdown] CancellationToken cleanup scheduler stop failed: %s", exc)
    finally:
        _cancellation_cleanup_scheduler_task = None


async def _login_session_cleanup_job() -> None:
    """Periodic login session cleanup (removes expired sessions)."""
    from app.channels.storage.login_session_registry import session_store

    try:
        deleted = await session_store.cleanup_expired(ttl_seconds=300.0)
        if deleted > 0:
            logger.info("Login session cleanup: %d expired sessions removed", deleted)
    except Exception as exc:
        logger.warning("Login session cleanup failed: %s", exc)


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
            manager.create_backup()
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


_db_maintenance_scheduler_task: asyncio.Task[None] | None = None


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
                await scheduler.add_schedule(
                    _db_maintenance_job,
                    IntervalTrigger(hours=6),
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


_login_session_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def start_login_session_cleanup_scheduler() -> None:
    """Start login session cleanup scheduler (every 5 minutes)."""
    global _login_session_cleanup_scheduler, _login_session_cleanup_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager."""
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _login_session_cleanup_job,
                    IntervalTrigger(minutes=5),
                    id="login_session_cleanup",
                )
                global _login_session_cleanup_scheduler
                _login_session_cleanup_scheduler = scheduler
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Login session cleanup scheduler started (every 5 min)")
                await asyncio.Event().wait()

        _login_session_cleanup_scheduler_task = spawn_observed_task(run_scheduler(), name="login_session_cleanup")

    except Exception as exc:
        logger.error("Failed to start login session cleanup scheduler: %s", exc)


async def stop_login_session_cleanup_scheduler() -> None:
    """Stop the login session cleanup scheduler."""
    global _login_session_cleanup_scheduler, _login_session_cleanup_scheduler_task

    if _login_session_cleanup_scheduler_task is None:
        return

    try:
        _login_session_cleanup_scheduler_task.cancel()
        try:
            await _login_session_cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Login session cleanup scheduler stopped")
    except Exception as exc:
        logger.error("[Shutdown] Login session cleanup scheduler stop failed: %s", exc)
    finally:
        _login_session_cleanup_scheduler = None
        _login_session_cleanup_scheduler_task = None


_auth_log_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def start_auth_log_cleanup_scheduler() -> None:
    """Start auth audit log cleanup scheduler (daily at 4:00 AM)."""
    global _auth_log_cleanup_scheduler, _auth_log_cleanup_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.cron import CronTrigger

        async def run_scheduler() -> None:
            """Run scheduler in context manager."""
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _auth_log_cleanup_job,
                    CronTrigger(hour=4, minute=0),
                    id="auth_log_cleanup",
                )
                global _auth_log_cleanup_scheduler
                _auth_log_cleanup_scheduler = scheduler
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Auth log cleanup scheduler started (daily at 04:00)")
                await asyncio.Event().wait()

        _auth_log_cleanup_scheduler_task = spawn_observed_task(run_scheduler(), name="auth_log_cleanup")

    except Exception as exc:
        logger.error("Failed to start auth log cleanup scheduler: %s", exc)


async def stop_auth_log_cleanup_scheduler() -> None:
    """Stop the auth log cleanup scheduler."""
    global _auth_log_cleanup_scheduler, _auth_log_cleanup_scheduler_task

    if _auth_log_cleanup_scheduler_task is None:
        return

    try:
        _auth_log_cleanup_scheduler_task.cancel()
        try:
            await _auth_log_cleanup_scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Auth log cleanup scheduler stopped")
    except Exception as exc:
        logger.error("[Shutdown] Auth log cleanup scheduler stop failed: %s", exc)
    finally:
        _auth_log_cleanup_scheduler = None
        _auth_log_cleanup_scheduler_task = None


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


async def start_kanban_dispatchers() -> None:
    """Start kanban dispatchers for all boards.

    1. Boot recovery: reset stale RUNNING → READY.
    2. Create KanbanTaskRunner and store on KanbanService for dynamic use.
    3. Wire PlatformTaskSpecifier for TRIAGE → spec rewrites.
    4. Start a dispatcher per board (dispatcher sleeps when no READY tasks).
    """
    from app.services.kanban import KanbanService
    from app.services.kanban.decompose import PlatformTaskDecomposer
    from app.services.kanban.specify import PlatformTaskSpecifier
    from app.services.kanban.task_runner import KanbanTaskRunner

    svc = KanbanService.get_instance()

    # Boot recovery: reclaim tasks that were RUNNING when the process exited
    await svc.recover_stale_tasks()

    runner = KanbanTaskRunner(svc.store)
    svc.set_runner(runner)

    svc.set_specifier(PlatformTaskSpecifier())
    svc.set_decomposer(PlatformTaskDecomposer())

    boards = await svc.list_boards()
    started = 0
    for board in boards:
        dispatcher = await svc.start_dispatcher(board.board_id, runner)
        if dispatcher is not None:
            started += 1

    logger.info("[Startup] Kanban dispatchers started for %d board(s)", started)


async def stop_kanban_dispatchers() -> None:
    """Stop all kanban dispatchers gracefully."""
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    await svc.shutdown()
    logger.info("[Shutdown] Kanban dispatchers stopped")


# ============================================================================
# Remote Backup Auto-Sync Scheduler
# ============================================================================

_remote_backup_scheduler_task: asyncio.Task[None] | None = None


def _section(config: dict[str, object], key: str) -> dict[str, object]:
    section = config.get(key)
    return section if isinstance(section, dict) else {}


def _text(config: dict[str, object], key: str, default: str = "") -> str:
    value = config.get(key)
    return value if isinstance(value, str) else default


def _flag(config: dict[str, object], key: str, default: bool) -> bool:
    value = config.get(key)
    return value if isinstance(value, bool) else default


def _count(config: dict[str, object], key: str, default: int) -> int:
    value = config.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


async def _remote_backup_auto_sync_job() -> None:
    """Periodic remote backup job. Reads config and syncs if enabled."""
    try:
        from app.services.config.service import config_service

        record = await config_service.get("backupSync")
        if not record:
            return

        value = record.value if hasattr(record, "value") else {}
        enabled = value.get("enabled", False)
        auto_sync = value.get("autoSync", False)

        if not enabled or not auto_sync:
            return

        provider = _text(value, "provider")
        if not provider:
            return

        from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager
        from app.services.memory.backup.backup_remote import (
            RemoteBackupStrategy,
            S3BackupConfig,
            S3BackupStrategy,
            WebDAVBackupConfig,
            WebDAVBackupStrategy,
        )
        from app.services.memory.backup.backup_remote_scheduler import run_remote_backup

        device_name = _text(value, "deviceName") or platform.node()
        max_backups = _count(value, "maxBackups", 10)

        strategy: RemoteBackupStrategy
        if provider == "webdav":
            webdav_cfg = _section(value, "webdav")
            strategy = WebDAVBackupStrategy(
                WebDAVBackupConfig(
                    host=_text(webdav_cfg, "host"),
                    username=_text(webdav_cfg, "username"),
                    password=_text(webdav_cfg, "password"),
                    path=_text(webdav_cfg, "path", "/myrm-backups"),
                )
            )
        elif provider == "s3":
            s3_cfg = _section(value, "s3")
            strategy = S3BackupStrategy(
                S3BackupConfig(
                    endpoint=_text(s3_cfg, "endpoint"),
                    region=_text(s3_cfg, "region"),
                    bucket=_text(s3_cfg, "bucket"),
                    access_key_id=_text(s3_cfg, "accessKeyId"),
                    secret_access_key=_text(s3_cfg, "secretAccessKey"),
                    prefix=_text(s3_cfg, "prefix", "myrm-backups/"),
                    force_path_style=_flag(s3_cfg, "forcePathStyle", True),
                )
            )
        else:
            logger.warning("Unknown backup provider: %s", provider)
            return

        result = await run_remote_backup(
            manager=await create_guardian_memory_manager(),
            strategy=strategy,
            device_name=device_name,
            max_backups=max_backups,
        )

        if result.get("success"):
            logger.info("Auto remote backup completed: %s", result.get("file_name"))
        else:
            logger.warning("Auto remote backup failed: %s", result.get("error"))

    except Exception as exc:
        logger.warning("Remote backup auto-sync job failed: %s", exc)


async def start_remote_backup_scheduler() -> None:
    """Start remote backup auto-sync scheduler.

    Default interval: 60 minutes (configurable via backupSync config).
    Only runs if backupSync.enabled and backupSync.autoSync are true.
    """
    global _remote_backup_scheduler_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _remote_backup_auto_sync_job,
                    IntervalTrigger(minutes=60),
                    id="remote_backup_auto_sync",
                )
                # APScheduler runs schedules only after an explicit start.
                await scheduler.start_in_background()
                logger.info("Remote backup auto-sync scheduler started (every 60 min)")
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
