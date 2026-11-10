"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- prepare_kanban_dispatch, start_kanban_dispatchers, stop_kanban_dispatchers

[POS]
Lifecycle schedulers: kanban dispatch preparation (boot, before the HTTP bind), dispatcher start (after the bind) and stop.
"""

from __future__ import annotations

from .common import logger

# The web UI's own first requests (readiness, config sync) are served before the dispatchers' first
# queries, which number a few per board.
BOOT_DISPATCH_DELAY_SECONDS = 2.0


async def prepare_kanban_dispatch() -> None:
    """Make kanban ready to dispatch; cheap, so it runs before the HTTP bind.

    1. Boot recovery: reset stale RUNNING → READY, once for every board.
    2. Create KanbanTaskRunner and store on KanbanService for dynamic use.
    3. Wire PlatformTaskSpecifier for TRIAGE → spec rewrites.
    """
    from app.services.kanban import KanbanService
    from app.services.kanban.decompose import PlatformTaskDecomposer
    from app.services.kanban.specify import PlatformTaskSpecifier
    from app.services.kanban.task_runner import KanbanTaskRunner

    svc = KanbanService.get_instance()

    # Boot recovery: reclaim tasks that were RUNNING when the process exited. This replaces the
    # per-board rescue inside KanbanDispatcher.start(), which the boot path skips.
    await svc.recover_stale_tasks()

    svc.set_runner(KanbanTaskRunner(svc.store))
    svc.set_specifier(PlatformTaskSpecifier())
    svc.set_decomposer(PlatformTaskDecomposer())


async def start_kanban_dispatchers() -> None:
    """Start a dispatcher per board in the background (a dispatcher sleeps when no READY tasks exist).

    Called once the HTTP server accepts requests: the boot does not wait for the dispatchers, so its
    length does not grow with the number of boards, and the first start is held back by
    ``BOOT_DISPATCH_DELAY_SECONDS``. The dispatchers share one boot gate: while no usable model
    configuration exists they leave READY tasks queued, so a boot cannot claim every queued task and
    record a failure for each.
    """
    from app.services.kanban import KanbanService

    KanbanService.get_instance().start_boot_dispatchers(start_after_seconds=BOOT_DISPATCH_DELAY_SECONDS)


async def stop_kanban_dispatchers() -> None:
    """Stop all kanban dispatchers gracefully."""
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    await svc.shutdown()
    logger.info("[Shutdown] Kanban dispatchers stopped")
