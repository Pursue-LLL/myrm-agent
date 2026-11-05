"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- _login_session_cleanup_scheduler, _auth_log_cleanup_scheduler, _approval_ttl_scheduler_task, _cancellation_cleanup_scheduler_task, _login_session_cleanup_scheduler_task, _auth_log_cleanup_scheduler_task, _approval_ttl_job, start_approval_ttl_scheduler, stop_approval_ttl_scheduler, _cancellation_token_cleanup_job, start_cancellation_cleanup_scheduler, stop_cancellation_cleanup_scheduler, _login_session_cleanup_job, start_login_session_cleanup_scheduler, stop_login_session_cleanup_scheduler, _auth_log_cleanup_job, start_auth_log_cleanup_scheduler, stop_auth_log_cleanup_scheduler

[POS]
Lifecycle schedulers: approval TTL, cancellation-token, login-session and auth-log cleanup.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.infra.background_task import spawn_observed_task

from .common import logger

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler

_login_session_cleanup_scheduler: AsyncScheduler | None = None


_auth_log_cleanup_scheduler: AsyncScheduler | None = None


_approval_ttl_scheduler_task: asyncio.Task[None] | None = None


_cancellation_cleanup_scheduler_task: asyncio.Task[None] | None = None


_login_session_cleanup_scheduler_task: asyncio.Task[None] | None = None


_auth_log_cleanup_scheduler_task: asyncio.Task[None] | None = None


async def _approval_ttl_job() -> None:
    """Periodic approval TTL job (rejects expired approvals)."""
    try:
        from app.services.approvals.registry import ApprovalRegistry

        rejected_count = await ApprovalRegistry.cleanup_expired_approvals()
        if rejected_count > 0:
            logger.info("Approval TTL cleanup: %d expired approvals rejected", rejected_count)
    except Exception as exc:
        logger.warning("Approval TTL cleanup failed: %s", exc)


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
