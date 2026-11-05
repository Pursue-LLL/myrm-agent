"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- _context_cleanup_scheduler, _context_cleanup_scheduler_task, _context_cleanup_job, start_context_cleanup_scheduler, stop_context_cleanup_scheduler, start_context_compaction_telemetry_dispatcher, stop_context_compaction_telemetry_dispatcher, start_memory_brief_status_telemetry_dispatcher, stop_memory_brief_status_telemetry_dispatcher, start_memory_guardian_guard_telemetry_dispatcher, stop_memory_guardian_guard_telemetry_dispatcher

[POS]
Lifecycle schedulers: context file cleanup and the three telemetry dispatchers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.infra.background_task import spawn_observed_task

from .common import logger

if TYPE_CHECKING:
    from apscheduler import AsyncScheduler

_context_cleanup_scheduler: AsyncScheduler | None = None


_context_cleanup_scheduler_task: asyncio.Task[None] | None = None


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

    try:
        from app.channels.media.image_enrichment import sweep_channel_image_cache

        removed_images = await asyncio.to_thread(sweep_channel_image_cache)
        if removed_images > 0:
            logger.info("Context cleanup: removed %d expired channel images", removed_images)
    except Exception as e:
        logger.warning(f"Channel image cache sweep failed: {e}")


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
