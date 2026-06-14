"""Integration Sync Daemon — scheduled background sync for knowledge sources.

[INPUT]
- app.services.memory.integration_memory (POS: IntegrationMemoryService facade)
- apscheduler (POS: Async scheduler for periodic tasks)

[OUTPUT]
- IntegrationSyncDaemon: Background daemon with configurable sync interval.
- start_integration_sync_daemon / stop_integration_sync_daemon: Lifecycle API.

[POS]
Reuses the APScheduler pattern already established in schedulers.py for
DB maintenance, context cleanup, etc.  Periodically invokes
IntegrationMemoryService.sync_all() to keep knowledge sources fresh.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_MINUTES = 60

_daemon_task: asyncio.Task[None] | None = None
_daemon_interval_minutes: int = _DEFAULT_INTERVAL_MINUTES


async def _sync_job() -> None:
    """Execute a full sync of all registered integration providers."""
    try:
        from app.services.memory.integration_memory import get_integration_memory_service

        svc = await get_integration_memory_service()
        if svc is None:
            return

        if not svc.provider_ids:
            return

        results = await svc.sync_all()
        total_created = sum(r.created for r in results)
        total_errors = sum(r.failed for r in results)

        if total_created > 0 or total_errors > 0:
            logger.info(
                "Integration sync completed: providers=%d, created=%d, errors=%d",
                len(results),
                total_created,
                total_errors,
            )
    except Exception as exc:
        logger.warning("Integration sync job failed: %s", exc)


async def start_integration_sync_daemon(interval_minutes: int = _DEFAULT_INTERVAL_MINUTES) -> None:
    """Start the background sync daemon with APScheduler."""
    global _daemon_task, _daemon_interval_minutes
    _daemon_interval_minutes = interval_minutes

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _sync_job,
                    IntervalTrigger(minutes=interval_minutes),
                    id="integration_knowledge_sync",
                )
                logger.info("Integration sync daemon started (every %d min)", interval_minutes)
                await asyncio.Event().wait()

        _daemon_task = asyncio.create_task(run_scheduler())

    except Exception as exc:
        logger.error("Failed to start integration sync daemon: %s", exc)


async def stop_integration_sync_daemon() -> None:
    """Stop the background sync daemon gracefully."""
    global _daemon_task

    if _daemon_task is None:
        return

    try:
        _daemon_task.cancel()
        try:
            await _daemon_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Integration sync daemon stopped")
    except Exception as exc:
        logger.error("[Shutdown] Integration sync daemon stop failed: %s", exc)
    finally:
        _daemon_task = None
