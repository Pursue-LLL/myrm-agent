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
