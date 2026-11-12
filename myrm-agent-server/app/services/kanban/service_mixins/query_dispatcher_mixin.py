"""KanbanService read/query and dispatcher lifecycle mixins.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- board_summary (POS: Board summary aggregation.)
- dispatcher_lifecycle (POS: Dispatcher lifecycle management.)
- query_ops (POS: Read-only queries.)
- service_mixins.core (POS: KanbanService core state.)

[OUTPUT]
- KanbanReadMixin: Mixin providing board, task, run and event query methods.
- KanbanDispatcherMixin: Mixin providing dispatcher lifecycle methods.

[POS]
Query and dispatcher mixin: board/task reads, event/run history, dispatcher start/stop/shutdown. The boot start runs
in the background and ends at a step boundary when the service shuts down.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import TaskRunner
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanBoard,
    KanbanTask,
    TaskEdge,
    TaskEvent,
    TaskRun,
    TaskStatus,
)
from sqlalchemy.exc import OperationalError

from app.core.infra.background_task import spawn_observed_task
from app.core.kanban.adapters.sqlalchemy_store import BoardEventRow
from app.services.kanban.board_summary import build_board_summary
from app.services.kanban.dispatcher_lifecycle import (
    recover_stale_tasks as run_recover_stale_tasks,
)
from app.services.kanban.dispatcher_lifecycle import (
    shutdown_dispatchers,
)
from app.services.kanban.dispatcher_lifecycle import (
    start_dispatcher as run_start_dispatcher,
)
from app.services.kanban.dispatcher_lifecycle import (
    stop_dispatcher as run_stop_dispatcher,
)
from app.services.kanban.event_publisher import publish_kanban_event as _publish_kanban_event
from app.services.kanban.query_ops import (
    add_comment as run_add_comment,
)
from app.services.kanban.query_ops import (
    clear_agent_references as run_clear_agent_references,
)
from app.services.kanban.query_ops import (
    get_board as run_get_board,
)
from app.services.kanban.query_ops import (
    get_task as run_get_task,
)
from app.services.kanban.query_ops import (
    list_board_edges as run_list_board_edges,
)
from app.services.kanban.query_ops import (
    list_board_events as run_list_board_events,
)
from app.services.kanban.query_ops import (
    list_boards as run_list_boards,
)
from app.services.kanban.query_ops import (
    list_events as run_list_events,
)
from app.services.kanban.query_ops import (
    list_runs as run_list_runs,
)
from app.services.kanban.query_ops import (
    list_task_dependencies as run_list_task_dependencies,
)
from app.services.kanban.query_ops import (
    list_task_dependents as run_list_task_dependents,
)
from app.services.kanban.query_ops import (
    list_tasks as run_list_tasks,
)
from app.services.kanban.service_mixins.core import KanbanServiceCore
from app.services.kanban.service_mixins.types import BoardSummaryData

logger = logging.getLogger(__name__)

# Boards whose dispatchers start between two pauses at boot, and the length of that pause.
_BOOT_BATCH_SIZE = 25
_BOOT_BATCH_PAUSE_SECONDS = 0.05

# How long a boot start gets to reach its next step boundary once the service shuts down, and again after the
# cancellation fallback, before it is abandoned.
_BOOT_START_GRACE_SECONDS = 5.0


async def _sleep_unless_stopped(stop: asyncio.Event, seconds: float) -> bool:
    """Wait up to ``seconds``; return True when ``stop`` is set, which ends the wait at once."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    return stop.is_set()


class KanbanReadMixin(KanbanServiceCore):
    async def get_board(self, board_id: str) -> KanbanBoard | None:
        return await run_get_board(self._store, board_id)

    async def list_boards(self, *, project_id: str | None = None) -> list[KanbanBoard]:
        return await run_list_boards(self._store, project_id=project_id)

    async def count_tasks_by_status(self, status: TaskStatus) -> int:
        """Count tasks in a given status across all boards.

        Degrades to 0 when the kanban schema is unavailable so aggregated
        statistics never fail on a missing kanban table.
        """
        try:
            boards = await run_list_boards(self._store)
            total = 0
            for board in boards:
                total += await self._store.count_tasks(board.board_id, status=status)
            return total
        except OperationalError:
            logger.warning(
                "Kanban count for status %s unavailable; degrading to 0",
                status.value,
            )
            return 0

    async def count_review_tasks_by_agent(self) -> dict[str | None, int]:
        """Count IN_REVIEW tasks grouped by agent across all boards.

        Degrades to an empty mapping when the kanban schema is unavailable so
        aggregated statistics never fail on a missing kanban table.
        """
        try:
            boards = await run_list_boards(self._store)
            by_agent: dict[str | None, int] = {}
            for board in boards:
                agent_counts = await self._store.count_tasks_by_agent(board.board_id)
                for agent_id, status_counts in agent_counts.items():
                    in_review = status_counts.get(TaskStatus.IN_REVIEW.value, 0)
                    if in_review:
                        by_agent[agent_id] = by_agent.get(agent_id, 0) + in_review
            return by_agent
        except OperationalError:
            logger.warning("Kanban schema unavailable; treating review counts as empty")
            return {}

    async def get_task(self, task_id: str) -> KanbanTask | None:
        return await run_get_task(self._store, task_id)

    async def list_tasks(
        self,
        board_id: str,
        *,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        source_chat_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[KanbanTask]:
        return await run_list_tasks(
            self._store,
            board_id,
            status=status,
            agent_id=agent_id,
            source_chat_id=source_chat_id,
            limit=limit,
            offset=offset,
        )

    async def list_task_dependencies(self, task_id: str) -> list[str]:
        return await run_list_task_dependencies(self._store, task_id)

    async def list_task_dependents(self, task_id: str) -> list[str]:
        return await run_list_task_dependents(self._store, task_id)

    async def list_board_edges(self, board_id: str) -> list[TaskEdge]:
        return await run_list_board_edges(self._store, board_id)

    async def clear_agent_references(self, agent_id: str) -> int:
        return await run_clear_agent_references(self._store, agent_id)

    async def list_runs(self, task_id: str) -> list[TaskRun]:
        return await run_list_runs(self._store, task_id)

    async def list_events(
        self,
        task_id: str,
        *,
        since_id: int | None = None,
    ) -> list[TaskEvent]:
        return await run_list_events(self._store, task_id, since_id=since_id)

    async def list_board_events(
        self,
        board_id: str,
        *,
        kinds: list[str] | None = None,
        assignee: str | None = None,
        since_id: int | None = None,
        since_time: datetime | None = None,
        limit: int = 50,
    ) -> list[BoardEventRow]:
        return await run_list_board_events(
            self._store,
            board_id,
            kinds=kinds,
            assignee=assignee,
            since_id=since_id,
            since_time=since_time,
            limit=limit,
        )

    async def add_comment(
        self,
        task_id: str,
        body: str,
        *,
        author: str = "user",
    ) -> TaskEvent:
        return await run_add_comment(
            self._store,
            task_id,
            body,
            author=author,
            publish_event=_publish_kanban_event,
        )

    async def board_summary(self, board_id: str) -> BoardSummaryData | None:
        return await build_board_summary(self._store, self._dispatchers, board_id)

    async def recover_stale_tasks(self) -> int:
        return await run_recover_stale_tasks(self._store)


class KanbanDispatcherMixin(KanbanServiceCore):
    if TYPE_CHECKING:
        # Provided by KanbanReadMixin in the composed KanbanService.
        async def list_boards(self, *, project_id: str | None = None) -> list[KanbanBoard]: ...

    async def start_dispatcher(
        self,
        board_id: str,
        runner: TaskRunner,
        worker_id: str | None = None,
    ) -> KanbanDispatcher | None:
        return await run_start_dispatcher(
            self._store,
            self._dispatchers,
            board_id,
            runner,
            worker_id=worker_id,
        )

    def start_boot_dispatchers(self, *, start_after_seconds: float = 0.0) -> None:
        """Start every board's dispatcher for a server boot in the background and return at once.

        A dispatcher issues its first queries as soon as it exists, so a machine with hundreds of boards
        would otherwise keep the server from answering until all of them had been through that burst.
        ``start_after_seconds`` holds the first start back so the caller's own first requests are served
        before it. A board whose dispatcher has not started yet loses nothing: the dispatcher scans for
        READY tasks when it starts. ``shutdown`` ends a start that is still waiting or going.
        """
        runner = self._runner
        if runner is None:
            raise RuntimeError("The kanban runner must be set before the boot dispatchers start")
        self._boot_stop = asyncio.Event()
        self._boot_dispatchers_task = spawn_observed_task(
            self._start_boot_dispatchers(runner, start_after_seconds), name="kanban-boot-dispatchers"
        )

    async def _start_boot_dispatchers(self, runner: TaskRunner, start_after_seconds: float) -> None:
        """Gated on a usable model configuration: while none exists the dispatchers hold their READY tasks,
        so a boot cannot fail queued work or write a failure row for every task.

        The stale-RUNNING reset runs once before this, which is why each dispatcher skips its own per-board
        rescue query. The gate is evaluated here only, when there is at least one board to start; a
        dispatcher re-checks it on every wake cycle through the memoised `dispatch_allowed`.

        A shutdown ends the start between two steps (the wait, the board listing, one dispatcher start): the
        waits wake at once and no further board is started, while a step in flight completes, so no database
        call is cancelled.
        """
        from app.services.kanban.dispatch_gate import dispatch_allowed

        if start_after_seconds > 0 and await _sleep_unless_stopped(self._boot_stop, start_after_seconds):
            return
        boards = await self.list_boards()
        if not boards or self._boot_stop.is_set():
            return
        gated = not await dispatch_allowed()
        started = 0
        for position, board in enumerate(boards, start=1):
            if self._boot_stop.is_set():
                break
            if board.board_id in self._dispatchers:
                # A board created while this start waited already has its live dispatcher; starting
                # again would stop it first.
                continue
            dispatcher = await run_start_dispatcher(
                self._store,
                self._dispatchers,
                board.board_id,
                runner,
                rescue_orphans=False,
                dispatch_allowed=dispatch_allowed if gated else None,
                board=board,
            )
            if dispatcher is not None:
                started += 1
            if position % _BOOT_BATCH_SIZE == 0 and await _sleep_unless_stopped(self._boot_stop, _BOOT_BATCH_PAUSE_SECONDS):
                # The pause lets requests and the rest of the boot in between the batches' first queries.
                break
        logger.info(
            "[Startup] Kanban dispatchers started for %d board(s)%s",
            started,
            "; their READY tasks wait for a model provider" if gated else "",
        )

    async def stop_dispatcher(self, board_id: str) -> bool:
        return await run_stop_dispatcher(self._dispatchers, board_id)

    async def shutdown(self) -> None:
        """End the boot start, then stop every dispatcher, none of them cancelled inside a database call."""
        self._boot_stop.set()
        await self._join_boot_start()
        await shutdown_dispatchers(self._dispatchers)

    async def _join_boot_start(self) -> None:
        """Wait for the boot start to leave at its step boundary; cancel it only if it does not.

        A cancelled database call can tear its connection down twice and leave the shutdown waiting on a
        worker thread that has already exited, so cancellation is the bounded fallback, and a start that
        outlives it too is abandoned with a warning so that the shutdown always goes on.
        """
        boot_start = self._boot_dispatchers_task
        if boot_start is None or boot_start.done():
            return
        _, pending = await asyncio.wait({boot_start}, timeout=_BOOT_START_GRACE_SECONDS)
        if not pending:
            return
        boot_start.cancel()
        _, abandoned = await asyncio.wait(pending, timeout=_BOOT_START_GRACE_SECONDS)
        if abandoned:
            logger.warning("The kanban boot start did not end after cancellation; abandoned")
