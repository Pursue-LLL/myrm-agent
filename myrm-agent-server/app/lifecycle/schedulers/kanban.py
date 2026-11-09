"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- start_kanban_dispatchers, stop_kanban_dispatchers

[POS]
Lifecycle schedulers: kanban dispatcher start/stop.
"""

from __future__ import annotations

from .common import logger


async def start_kanban_dispatchers() -> None:
    """Start kanban dispatchers for all boards.

    1. Boot recovery: reset stale RUNNING → READY, once for every board.
    2. Create KanbanTaskRunner and store on KanbanService for dynamic use.
    3. Wire PlatformTaskSpecifier for TRIAGE → spec rewrites.
    4. Start a dispatcher per board (dispatcher sleeps when no READY tasks).

    The dispatchers share one boot gate: while no usable model configuration exists they leave
    READY tasks queued, so a boot cannot claim every queued task and record a failure for each.
    """
    from app.services.kanban import KanbanService
    from app.services.kanban.decompose import PlatformTaskDecomposer
    from app.services.kanban.specify import PlatformTaskSpecifier
    from app.services.kanban.task_runner import KanbanTaskRunner

    svc = KanbanService.get_instance()

    # Boot recovery: reclaim tasks that were RUNNING when the process exited. This replaces the
    # per-board rescue inside KanbanDispatcher.start(), which the boot path now skips.
    await svc.recover_stale_tasks()

    runner = KanbanTaskRunner(svc.store)
    svc.set_runner(runner)

    svc.set_specifier(PlatformTaskSpecifier())
    svc.set_decomposer(PlatformTaskDecomposer())

    started, gated = await svc.start_boot_dispatchers(runner)
    logger.info(
        "[Startup] Kanban dispatchers started for %d board(s)%s",
        started,
        "; their READY tasks wait for a model provider" if gated else "",
    )


async def stop_kanban_dispatchers() -> None:
    """Stop all kanban dispatchers gracefully."""
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    await svc.shutdown()
    logger.info("[Shutdown] Kanban dispatchers stopped")
