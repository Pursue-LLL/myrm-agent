"""KanbanService board and task mutation methods."""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskEdge,
    TaskPriority,
    TaskStatus,
)

from app.services.kanban.board_ops import (
    create_board as run_create_board,
)
from app.services.kanban.board_ops import (
    delete_board as run_delete_board,
)
from app.services.kanban.board_ops import (
    update_active_tasks_branch_metadata as run_update_branch_metadata,
)
from app.services.kanban.board_ops import (
    update_board as run_update_board,
)
from app.services.kanban.dependency_ops import (
    add_dependency as run_add_dependency,
)
from app.services.kanban.dependency_ops import (
    promote_task as run_promote_task,
)
from app.services.kanban.dependency_ops import (
    remove_dependency as run_remove_dependency,
)
from app.services.kanban.move_orchestrator import (
    cancel_task_execution as run_cancel_task_execution,
)
from app.services.kanban.move_orchestrator import (
    move_task as run_move_task,
)
from app.services.kanban.move_orchestrator import (
    reclaim_task as run_reclaim_task,
)
from app.services.kanban.service_core import KanbanServiceCore
from app.services.kanban.service_types import UNSET, PromoteResult, Sentinel
from app.services.kanban.task_ops import (
    add_task as run_add_task,
)
from app.services.kanban.task_ops import (
    delete_task as run_delete_task,
)
from app.services.kanban.task_ops import (
    update_task as run_update_task,
)


class KanbanBoardTaskMixin(KanbanServiceCore):
    async def create_board(
        self,
        name: str,
        description: str = "",
        settings: BoardSettings | None = None,
    ) -> KanbanBoard:
        return await run_create_board(
            self._store,
            name,
            description,
            settings,
            runner=self._runner,
            start_dispatcher=self.start_dispatcher,
        )

    async def update_active_tasks_branch_metadata(
        self,
        new_branch: str,
        old_branch: str | None = None,
        migrated: bool = False,
        board_id: str | None = None,
    ) -> int:
        return await run_update_branch_metadata(
            self._store, new_branch, old_branch, migrated, board_id
        )

    async def update_board(
        self,
        board_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        settings: BoardSettings | None = None,
    ) -> KanbanBoard | None:
        return await run_update_board(
            self._store,
            board_id,
            name=name,
            description=description,
            settings=settings,
        )

    async def delete_board(self, board_id: str) -> bool:
        return await run_delete_board(self._store, self._dispatchers, board_id)

    async def add_task(
        self,
        board_id: str,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        parent_task_id: str | None = None,
        agent_id: str | None = None,
        max_retries: int = 3,
        depends_on: list[str] | None = None,
        extra_skill_ids: list[str] | None = None,
        completion_criteria: str | None = None,
        initial_status: TaskStatus | None = None,
        max_runtime_seconds: int | None = None,
        workspace_path: str | None = None,
        branch: str | None = None,
    ) -> KanbanTask:
        return await run_add_task(
            self._store,
            self._dispatchers,
            board_id,
            title,
            description,
            priority,
            parent_task_id,
            agent_id,
            max_retries,
            depends_on,
            extra_skill_ids,
            completion_criteria,
            initial_status,
            max_runtime_seconds,
            workspace_path,
            branch,
            validate_agent_id=self._validate_agent_id,
            wake_dispatcher=self._wake_dispatcher,
        )

    async def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: TaskPriority | None = None,
        agent_id: str | None | Sentinel = UNSET,
        extra_skill_ids: list[str] | None | Sentinel = UNSET,
        max_runtime_seconds: int | None | Sentinel = UNSET,
        completion_criteria: str | None = None,
    ) -> KanbanTask | None:
        return await run_update_task(
            self._store,
            task_id,
            title=title,
            description=description,
            priority=priority,
            agent_id=agent_id,
            extra_skill_ids=extra_skill_ids,
            max_runtime_seconds=max_runtime_seconds,
            completion_criteria=completion_criteria,
            validate_agent_id=self._validate_agent_id,
        )

    async def move_task(
        self,
        task_id: str,
        target_status: TaskStatus,
        *,
        force: bool = False,
        block_kind: BlockKind | None = None,
        blocked_reason: str | None = None,
        scheduled_until: datetime | None = None,
        result: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> KanbanTask | None:
        return await run_move_task(
            self._store,
            self._dispatchers,
            self._runner,
            task_id,
            target_status,
            force=force,
            block_kind=block_kind,
            blocked_reason=blocked_reason,
            scheduled_until=scheduled_until,
            result=result,
            metadata=metadata,
            wake_dispatcher=self._wake_dispatcher,
        )

    async def cancel_task_execution(self, task_id: str) -> bool:
        return await run_cancel_task_execution(self._store, self._dispatchers, task_id)

    async def reclaim_task(
        self,
        task_id: str,
        *,
        reason: str | None = None,
        new_agent_id: str | None = None,
    ) -> KanbanTask | None:
        return await run_reclaim_task(
            self._store,
            self._dispatchers,
            task_id,
            reason=reason,
            new_agent_id=new_agent_id,
            validate_agent_id=self._validate_agent_id,
        )

    async def delete_task(self, task_id: str) -> bool:
        return await run_delete_task(self._store, task_id)

    async def add_dependency(self, child_task_id: str, parent_task_id: str) -> TaskEdge:
        return await run_add_dependency(self._store, child_task_id, parent_task_id)

    async def remove_dependency(self, child_task_id: str, parent_task_id: str) -> bool:
        return await run_remove_dependency(self._store, child_task_id, parent_task_id)

    async def promote_task(
        self,
        task_id: str,
        *,
        force: bool = False,
        reason: str | None = None,
    ) -> PromoteResult:
        return await run_promote_task(
            self._store,
            self._dispatchers,
            task_id,
            force=force,
            reason=reason,
            wake_dispatcher=self._wake_dispatcher,
        )
