"""KanbanService read/query and dispatcher lifecycle mixins.

[INPUT]
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- board_summary (POS: Board summary aggregation.)
- dispatcher_lifecycle (POS: Dispatcher lifecycle management.)
- query_ops (POS: Read-only queries.)
- service_core (POS: KanbanService core state.)

[OUTPUT]
- KanbanServiceQueryDispatcherMixin: Mixin providing query and dispatcher lifecycle methods.

[POS]
Query and dispatcher mixin: board/task reads, event/run history, dispatcher start/stop/shutdown.
"""

from __future__ import annotations

from datetime import datetime

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
from app.services.kanban.service_core import KanbanServiceCore
from app.services.kanban.service_types import BoardSummaryData


class KanbanReadMixin(KanbanServiceCore):
    async def get_board(self, board_id: str) -> KanbanBoard | None:
        return await run_get_board(self._store, board_id)

    async def list_boards(self) -> list[KanbanBoard]:
        return await run_list_boards(self._store)

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
    ) -> list[dict]:
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

    async def stop_dispatcher(self, board_id: str) -> bool:
        return await run_stop_dispatcher(self._dispatchers, board_id)

    async def shutdown(self) -> None:
        await shutdown_dispatchers(self._dispatchers)
