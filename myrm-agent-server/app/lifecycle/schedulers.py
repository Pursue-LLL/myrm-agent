"""Application lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler


logger = logging.getLogger(__name__)

_context_cleanup_scheduler: AsyncScheduler | None = None

_db_maintenance_scheduler: AsyncScheduler | None = None

_login_session_cleanup_scheduler: AsyncScheduler | None = None

_auth_log_cleanup_scheduler: AsyncScheduler | None = None


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
    from myrm_agent_harness.runtime.context.offload import cleanup_orphan_context_files_async

    checkpointer = None
    access_tracker = None
    try:
        from myrm_agent_harness.runtime.context.file_access_tracker import get_file_access_tracker

        from app.platform_utils import get_checkpointer

        checkpointer = get_checkpointer()
        access_tracker = await get_file_access_tracker()
    except Exception as exc:
        logger.debug("Checkpointer/tracker unavailable for cleanup: %s", exc)

    try:
        removed_count = await cleanup_orphan_context_files_async(
            max_age_days=7,
            session_active_days=30,
            file_access_days=14,
            checkpointer=checkpointer,
            access_tracker=access_tracker,
        )
        logger.info(
            f"Context cleanup: removed {removed_count} orphan files "
            f"(strategy: session-aware, active=30d, access=14d, fallback=7d)"
        )
    except Exception as e:
        logger.error(f"Context cleanup failed: {e}", exc_info=True)


async def start_cron_scheduler() -> None:
    """启动 Cron Scheduler（定时任务调度器）"""
    from app.core.cron.adapters.setup import get_cron_scheduler

    await get_cron_scheduler().start()
    logger.info("Cron scheduler started")


_context_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def start_context_cleanup_scheduler() -> None:
    """Start context file cleanup scheduler with session-aware strategy.

    Cleanup strategy:
    1. If session active within 30 days → keep all files
    2. Else if file accessed within 14 days → keep file
    3. Else → remove file

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
                logger.info("Context cleanup scheduler started (daily at 03:00, session-aware strategy)")
                # Run until cancelled
                await asyncio.Event().wait()

        _context_cleanup_scheduler_task = asyncio.create_task(run_scheduler())

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
                logger.info("Approval TTL scheduler started (every 5 min)")
                await asyncio.Event().wait()

        _approval_ttl_scheduler_task = asyncio.create_task(run_scheduler())

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


async def _login_session_cleanup_job() -> None:
    """Periodic login session cleanup (removes expired sessions)."""
    from app.api.channels.login import session_store

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
    3. Qdrant segment optimization — stable query performance
    4. Browser thread cleanup — zombie detection + old record deletion
    5. Memory import review cleanup — remove rollback-expired import sessions
    """
    # SQLite WAL checkpoint
    try:
        from sqlalchemy import text

        from app.platform_utils import session_factory

        async with session_factory() as session:
            result = await session.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            row = result.fetchone()
            if row:
                logger.info("SQLite WAL checkpoint: busy=%s, log=%s, checkpointed=%s", row[0], row[1], row[2])
            else:
                logger.info("SQLite WAL checkpoint completed")
    except Exception as e:
        logger.warning("SQLite WAL checkpoint failed: %s", e)

    # Database Backup (integrity-verified rotated snapshot)
    try:
        from app.database.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            manager.create_backup()
            logger.info("Periodic database backup completed")
    except Exception as e:
        logger.warning("Periodic database backup failed: %s", e)

    # Qdrant segment optimization (if store is active)
    try:
        from app.core.retriever.vector.defaults import create_default_vector_store

        store = await create_default_vector_store()
        if store is not None and hasattr(store, "_client"):
            from qdrant_client import AsyncQdrantClient

            client = store._client
            if isinstance(client, AsyncQdrantClient):
                collections = await client.get_collections()
                for col in collections.collections:
                    await client.update_collection(
                        collection_name=col.name,
                        optimizer_config={"indexing_threshold": 10000},
                    )
                logger.info("Qdrant optimize: %d collections updated", len(collections.collections))
    except ImportError:
        pass
    except Exception as e:
        logger.warning("Qdrant segment optimization failed: %s", e)

    # Browser thread cleanup (zombie detection + old record pruning)
    try:
        from .browser import cleanup_browser_threads

        await cleanup_browser_threads()
    except Exception as e:
        logger.warning("Periodic thread cleanup failed: %s", e)

    # Memory import review cleanup
    try:
        from app.platform_utils import session_factory
        from app.services.memory.import_sessions import MemoryImportSessionService

        async with session_factory() as session:
            deleted = await MemoryImportSessionService(session).cleanup_sessions()
        if deleted > 0:
            logger.info("Memory import review cleanup: %d expired review sessions removed", deleted)
    except Exception as e:
        logger.warning("Memory import review cleanup failed: %s", e)

    # Chat trash auto-purge: permanently delete chats trashed > 30 days
    try:
        from datetime import datetime as dt
        from datetime import timedelta

        from app.database.repositories.chat_repo import ChatRepository
        from app.platform_utils import session_factory
        from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

        cutoff = dt.utcnow() - timedelta(days=30)
        async with session_factory() as session:
            expired_ids = await ChatRepository.get_expired_trashed_chat_ids(session, cutoff)
            if expired_ids:
                for cid in expired_ids:
                    await ConversationRecallIndexService.delete_chat(session, cid)
                from sqlalchemy import delete as sa_delete

                from app.database.models import Chat

                await session.execute(sa_delete(Chat).where(Chat.id.in_(expired_ids)))
                await session.commit()
                logger.info("Chat trash auto-purge: %d expired chats permanently deleted", len(expired_ids))

        if expired_ids:
            from app.services.chat.chat_crud import _ChatCrudMixin
            from app.services.infra.sandbox_cleanup import cleanup_chat_workspace

            for cid in expired_ids:
                await _ChatCrudMixin._cleanup_checkpointer(cid)
                try:
                    await cleanup_chat_workspace(cid)
                except Exception as ws_err:
                    logger.warning("Chat trash auto-purge workspace cleanup failed (chat=%s): %s", cid, ws_err)
    except Exception as e:
        logger.warning("Chat trash auto-purge failed: %s", e)


async def _incognito_cleanup_job() -> None:
    """Incognito chat auto-purge: permanently delete incognito chats older than 1 hour"""
    try:
        from datetime import datetime as dt
        from datetime import timedelta

        from sqlalchemy import delete as sa_delete
        from sqlalchemy import select

        from app.database.models import Chat
        from app.platform_utils import session_factory
        from app.services.chat.conversation_recall_index_service import ConversationRecallIndexService

        cutoff = dt.utcnow() - timedelta(hours=1)
        async with session_factory() as session:
            stmt = select(Chat.id).where(Chat.is_incognito.is_(True), Chat.updated_at < cutoff)
            result = await session.execute(stmt)
            expired_incognito_ids = [row[0] for row in result.fetchall()]

            if expired_incognito_ids:
                for cid in expired_incognito_ids:
                    await ConversationRecallIndexService.delete_chat(session, cid)

                await session.execute(sa_delete(Chat).where(Chat.id.in_(expired_incognito_ids)))
                await session.commit()
                logger.info(
                    "Incognito chat auto-purge: %d expired incognito chats permanently deleted", len(expired_incognito_ids)
                )

        if expired_incognito_ids:
            from app.services.chat.chat_crud import _ChatCrudMixin
            from app.services.infra.sandbox_cleanup import cleanup_chat_workspace

            for cid in expired_incognito_ids:
                await _ChatCrudMixin._cleanup_checkpointer(cid)
                try:
                    await cleanup_chat_workspace(cid)
                except Exception as ws_err:
                    logger.warning("Incognito chat auto-purge workspace cleanup failed (chat=%s): %s", cid, ws_err)
    except Exception as e:
        logger.warning("Incognito chat auto-purge failed: %s", e)


_db_maintenance_scheduler_task: asyncio.Task[None] | None = None


async def start_db_maintenance_scheduler() -> None:
    """Start database maintenance scheduler (every 6 hours)."""
    global _db_maintenance_scheduler, _db_maintenance_scheduler_task

    try:
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
                global _db_maintenance_scheduler
                _db_maintenance_scheduler = scheduler
                logger.info("DB maintenance scheduler started (every 6 hours)")
                await asyncio.Event().wait()

        _db_maintenance_scheduler_task = asyncio.create_task(run_scheduler())
        logger.info("Database maintenance scheduler started (every 6h: WAL checkpoint + Qdrant optimize)")

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
                logger.info("Login session cleanup scheduler started (every 5 min)")
                await asyncio.Event().wait()

        _login_session_cleanup_scheduler_task = asyncio.create_task(run_scheduler())
        logger.info("Login session cleanup scheduler started (every 5min: remove expired sessions)")

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
                logger.info("Auth log cleanup scheduler started (daily at 04:00)")
                await asyncio.Event().wait()

        _auth_log_cleanup_scheduler_task = asyncio.create_task(run_scheduler())
        logger.info("Auth log cleanup scheduler started (daily at 04:00: remove old archives)")

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
    from app.services.kanban.decomposer import PlatformTaskDecomposer
    from app.services.kanban.specifier import PlatformTaskSpecifier
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

        provider = value.get("provider", "")
        if not provider:
            return

        from app.services.memory.backup_remote import (
            S3BackupConfig,
            S3BackupStrategy,
            WebDAVBackupConfig,
            WebDAVBackupStrategy,
        )
        from app.services.memory.backup_remote_scheduler import run_remote_backup

        device_name = value.get("deviceName", "") or platform.node()
        max_backups = value.get("maxBackups", 10)

        if provider == "webdav":
            webdav_cfg = value.get("webdav", {})
            strategy = WebDAVBackupStrategy(
                WebDAVBackupConfig(
                    host=webdav_cfg.get("host", ""),
                    username=webdav_cfg.get("username", ""),
                    password=webdav_cfg.get("password", ""),
                    path=webdav_cfg.get("path", "/myrm-backups"),
                )
            )
        elif provider == "s3":
            s3_cfg = value.get("s3", {})
            strategy = S3BackupStrategy(
                S3BackupConfig(
                    endpoint=s3_cfg.get("endpoint", ""),
                    region=s3_cfg.get("region", ""),
                    bucket=s3_cfg.get("bucket", ""),
                    access_key_id=s3_cfg.get("accessKeyId", ""),
                    secret_access_key=s3_cfg.get("secretAccessKey", ""),
                    prefix=s3_cfg.get("prefix", "myrm-backups/"),
                    force_path_style=s3_cfg.get("forcePathStyle", True),
                )
            )
        else:
            logger.warning("Unknown backup provider: %s", provider)
            return

        result = await run_remote_backup(
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
                logger.info("Remote backup auto-sync scheduler started (every 60 min)")
                await asyncio.Event().wait()

        _remote_backup_scheduler_task = asyncio.create_task(run_scheduler())

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
