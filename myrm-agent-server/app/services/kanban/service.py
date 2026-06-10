"""Kanban business service.

Orchestrates store, dispatcher, and EventBus for kanban operations.
Provides a clean API for the HTTP layer.

[INPUT]
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- myrm_agent_harness.toolkits.kanban (POS: Kanban toolkit framework layer.)
- api.events.event_bus::AppEvent, AppEventType, get_event_bus (POS: Global SSE event bus.)

[OUTPUT]
- KanbanService: Singleton business orchestration service.
- BoardSummaryData: Strongly-typed board summary dataclass.
- DependencyUnmetError: Raised when move_task targets READY with unmet parent dependencies.
- _publish_kanban_event: Module-level helper publishing kanban events to EventBus.

[POS]
Kanban business service.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar, TypedDict

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.protocols import (
    DecomposeChildSpec,
    DecomposeOutcome,
    SpecifyOutcome,
    TaskDecomposer,
    TaskRunner,
    TaskSpecifier,
)
from myrm_agent_harness.toolkits.kanban.types import (
    _TRIAGE_ALLOWED_TARGETS,
    BlockKind,
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskEdge,
    TaskEvent,
    TaskEventKind,
    TaskPriority,
    TaskRun,
    TaskRunOutcome,
    TaskStatus,
)

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.kanban.decompose_orchestrator import (
    run_apply_decompose,
    run_apply_no_fanout,
    run_decompose_task,
)
from app.services.kanban.specify_orchestrator import (
    SPECIFY_ALL_MAX_CONCURRENT,
    run_apply_spec,
    run_specify_all_triage,
    run_specify_task,
)


@dataclass(frozen=True, slots=True)
class BoardSummaryData:
    """Strongly-typed board summary returned by KanbanService.board_summary."""

    board: KanbanBoard
    task_counts: dict[str, int]
    total_tasks: int
    dispatcher_active: bool
    by_agent: dict[str | None, dict[str, int]] = field(default_factory=dict)
    oldest_ready_age_seconds: int | None = None


class UnmetParentInfo(TypedDict):
    task_id: str
    title: str
    status: str


@dataclass(frozen=True, slots=True)
class PromoteResult:
    """Result of a promote_task operation."""

    promoted: bool
    forced: bool = False
    reason: str | None = None
    unmet_parents: list[UnmetParentInfo] = field(default_factory=list)


class _Sentinel(enum.Enum):
    """Distinguishes 'not provided' from explicit None (clear agent_id)."""

    UNSET = "UNSET"


_UNSET = _Sentinel.UNSET

logger = logging.getLogger(__name__)


def _publish_kanban_event(
    board_id: str,
    task_id: str,
    action: str,
    *,
    title: str = "",
    detail: str = "",
    status: str = "",
) -> None:
    """Publish a kanban task update event to the global SSE event bus."""
    data: dict[str, str] = {
        "board_id": board_id,
        "task_id": task_id,
        "action": action,
    }
    if title:
        data["title"] = title
    if detail:
        data["detail"] = detail
    if status:
        data["status"] = status
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data=data,
        )
    )


_BTW_TERMINAL_EVENTS = frozenset({"task_completed", "task_failed"})


def _emit_btw_done(event_type: str, task: KanbanTask) -> None:
    """Publish BACKGROUND_TASK_DONE when a /btw task reaches a terminal state.

    Runs synchronously inside KanbanDispatcher.emit(); the actual channel
    delivery is handled asynchronously by BtwTaskNotifier subscribing to
    the EventBus.
    """
    if event_type not in _BTW_TERMINAL_EVENTS:
        return
    meta = task.metadata or {}
    if meta.get("background_source") != "btw":
        return
    channel = meta.get("channel")
    chat_id = meta.get("chat_id")
    if not channel or not chat_id:
        return
    get_event_bus().publish(
        AppEvent(
            event_type=AppEventType.BACKGROUND_TASK_DONE,
            data={
                "task_id": task.task_id,
                "status": "completed" if event_type == "task_completed" else "failed",
                "title": task.title,
                "result": task.result or task.error or "",
                "channel": channel,
                "chat_id": chat_id,
                "thread_id": meta.get("thread_id", ""),
                "user_id": meta.get("user_id", ""),
                "locale": meta.get("locale", "en"),
            },
        )
    )


class DependencyUnmetError(ValueError):
    """Raised when a task cannot be promoted to READY due to unmet parent dependencies."""

    def __init__(
        self,
        task_id: str,
        unsatisfied: list[str],
        unmet_details: list[UnmetParentInfo] | None = None,
    ) -> None:
        self.task_id = task_id
        self.unsatisfied = unsatisfied
        self.unmet_details: list[UnmetParentInfo] = unmet_details or []
        super().__init__(f"Task {task_id} has unmet dependencies: {', '.join(unsatisfied)}")


_STATUS_TO_EVENT_KIND: dict[TaskStatus, TaskEventKind] = {
    TaskStatus.BLOCKED: TaskEventKind.BLOCKED,
    TaskStatus.ARCHIVED: TaskEventKind.ARCHIVED,
    TaskStatus.COMPLETED: TaskEventKind.COMPLETED,
    TaskStatus.FAILED: TaskEventKind.FAILED,
}


class KanbanService:
    """Singleton business orchestration service for kanban.

    Manages the lifecycle of boards, tasks, and dispatchers.
    """

    _instance: ClassVar[KanbanService | None] = None

    def __init__(self) -> None:
        self._store = SqlAlchemyKanbanStore()
        self._dispatchers: dict[str, KanbanDispatcher] = {}
        self._runner: TaskRunner | None = None
        self._specifier: TaskSpecifier | None = None
        self._decomposer: TaskDecomposer | None = None

    @classmethod
    def get_instance(cls) -> KanbanService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def store(self) -> SqlAlchemyKanbanStore:
        return self._store

    def set_runner(self, runner: TaskRunner) -> None:
        """Store the TaskRunner for dynamic dispatcher creation."""
        self._runner = runner

    def set_specifier(self, specifier: TaskSpecifier) -> None:
        """Inject the TaskSpecifier used by ``specify_task`` / ``specify_all``."""
        self._specifier = specifier

    @property
    def specifier(self) -> TaskSpecifier | None:
        """Expose the current TaskSpecifier (None if not yet injected)."""
        return self._specifier

    def set_decomposer(self, decomposer: TaskDecomposer) -> None:
        """Inject the TaskDecomposer used by ``decompose_task`` / ``apply_decompose``."""
        self._decomposer = decomposer

    @property
    def decomposer(self) -> TaskDecomposer | None:
        """Expose the current TaskDecomposer (None if not yet injected)."""
        return self._decomposer

    # -- Board operations --

    async def create_board(
        self,
        name: str,
        description: str = "",
        settings: BoardSettings | None = None,
    ) -> KanbanBoard:
        board = KanbanBoard(
            board_id=uuid.uuid4().hex[:12],
            name=name,
            description=description,
            settings=settings or BoardSettings(),
        )
        saved = await self._store.save_board(board)
        if self._runner is not None:
            await self.start_dispatcher(saved.board_id, self._runner)
        return saved

    async def update_active_tasks_branch_metadata(
        self, new_branch: str, old_branch: str | None = None, migrated: bool = False, board_id: str | None = None
    ) -> int:
        """Update branch metadata for all active tasks when workspace branch changes."""
        updated_tasks = await self._store.update_active_tasks_branch_metadata(new_branch, old_branch, migrated, board_id)
        for task in updated_tasks:
            _publish_kanban_event(task.board_id, task.task_id, "updated", title=task.title)
        return len(updated_tasks)

    async def get_board(self, board_id: str) -> KanbanBoard | None:
        return await self._store.get_board(board_id)

    async def list_boards(self) -> list[KanbanBoard]:
        return await self._store.list_boards()

    async def update_board(
        self,
        board_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        settings: BoardSettings | None = None,
    ) -> KanbanBoard | None:
        board = await self._store.get_board(board_id)
        if board is None:
            return None
        if name is not None:
            board.name = name
        if description is not None:
            board.description = description
        if settings is not None:
            board.settings = settings
        return await self._store.save_board(board)

    async def delete_board(self, board_id: str) -> bool:
        if board_id in self._dispatchers:
            await self._dispatchers[board_id].stop()
            del self._dispatchers[board_id]
        return await self._store.delete_board(board_id)

    # -- Task operations --

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
        if agent_id is not None:
            await self._validate_agent_id(agent_id)

        if initial_status is None:
            resolved_status = TaskStatus.BACKLOG if depends_on else TaskStatus.READY
        elif initial_status == TaskStatus.TRIAGE:
            resolved_status = TaskStatus.TRIAGE
        elif initial_status in (TaskStatus.READY, TaskStatus.BACKLOG, TaskStatus.BLOCKED):
            if initial_status == TaskStatus.READY and depends_on:
                resolved_status = TaskStatus.BACKLOG
            else:
                resolved_status = initial_status
        else:
            raise ValueError(f"initial_status must be one of TRIAGE/BACKLOG/READY/BLOCKED, got {initial_status}")

        metadata: dict[str, object] = {}
        if completion_criteria:
            metadata["completion_criteria"] = completion_criteria

        # Inject current git branch into metadata
        from app.services.agent.goal_registry import get_current_git_branch

        current_branch = await get_current_git_branch()
        if current_branch:
            metadata["branch"] = current_branch

        task = KanbanTask(
            task_id=uuid.uuid4().hex[:12],
            board_id=board_id,
            title=title,
            description=description,
            status=resolved_status,
            priority=priority,
            agent_id=agent_id,
            parent_task_id=parent_task_id,
            workspace_path=workspace_path,
            branch=branch,
            max_runtime_seconds=max_runtime_seconds,
            extra_skill_ids=extra_skill_ids or [],
            max_retries=max_retries,
            metadata=metadata,
        )
        saved = await self._store.save_task(task)
        await self._store.append_event(saved.task_id, TaskEventKind.CREATED)

        if depends_on:
            valid_deps: list[str] = []
            for pid in depends_on:
                parent = await self._store.get_task(pid)
                if parent is None:
                    logger.warning("Skipped dependency %s -> %s (parent not found)", pid, saved.task_id)
                    continue
                valid_deps.append(pid)
            for pid in valid_deps:
                try:
                    await self._store.add_edge(pid, saved.task_id)
                except ValueError:
                    logger.warning(
                        "Skipped dependency %s -> %s (cycle detected)",
                        pid,
                        saved.task_id,
                    )
            if not valid_deps and depends_on:
                saved.status = TaskStatus.READY
                saved = await self._store.save_task(saved)

        if board_id in self._dispatchers:
            self._dispatchers[board_id].wake()
        _publish_kanban_event(board_id, saved.task_id, "created", title=saved.title)
        return saved

    async def get_task(self, task_id: str) -> KanbanTask | None:
        return await self._store.get_task(task_id)

    async def list_tasks(
        self,
        board_id: str,
        *,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[KanbanTask]:
        return await self._store.list_tasks(board_id, status=status, agent_id=agent_id, limit=limit, offset=offset)

    async def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: TaskPriority | None = None,
        agent_id: str | None | _Sentinel = _UNSET,
        extra_skill_ids: list[str] | None | _Sentinel = _UNSET,
        max_runtime_seconds: int | None | _Sentinel = _UNSET,
        completion_criteria: str | None = None,
    ) -> KanbanTask | None:
        task = await self._store.get_task(task_id)
        if task is None:
            return None
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if priority is not None:
            task.priority = priority
        old_agent_id: str | None = task.agent_id
        agent_changed = False
        if not isinstance(agent_id, _Sentinel):
            if agent_id is not None and agent_id != task.agent_id:
                await self._validate_agent_id(agent_id)
            if agent_id != task.agent_id:
                agent_changed = True
                task.consecutive_failures = 0
                task.error = ""
            task.agent_id = agent_id
        if not isinstance(extra_skill_ids, _Sentinel):
            task.extra_skill_ids = extra_skill_ids or []
        if not isinstance(max_runtime_seconds, _Sentinel):
            task.max_runtime_seconds = max_runtime_seconds
        if completion_criteria is not None:
            if completion_criteria:
                task.metadata["completion_criteria"] = completion_criteria
            else:
                task.metadata.pop("completion_criteria", None)
        saved = await self._store.save_task(task)
        _publish_kanban_event(saved.board_id, task_id, "updated", title=saved.title)
        if agent_changed:
            await self._store.append_event(
                task_id,
                TaskEventKind.ASSIGNED,
                payload={
                    "old_agent_id": old_agent_id,
                    "new_agent_id": saved.agent_id,
                },
            )
        return saved

    async def move_task(
        self,
        task_id: str,
        target_status: TaskStatus,
        *,
        force: bool = False,
        block_kind: BlockKind | None = None,
        blocked_reason: str | None = None,
        scheduled_until: datetime | None = None,
    ) -> KanbanTask | None:
        task = await self._store.get_task(task_id)
        if task is None:
            return None
        if task.is_terminal and target_status != TaskStatus.ARCHIVED:
            raise ValueError(f"Cannot move terminal task (status={task.status}) to {target_status}")
        if task.status == TaskStatus.TRIAGE and target_status not in _TRIAGE_ALLOWED_TARGETS:
            raise ValueError(f"TRIAGE task can only move to BACKLOG/READY/ARCHIVED, got {target_status}")
        old_status = task.status
        task.status = target_status
        unsatisfied_deps: list[str] = []
        if target_status == TaskStatus.BLOCKED:
            task.block_kind = block_kind or BlockKind.HUMAN
            task.scheduled_until = scheduled_until
            if blocked_reason:
                task.blocked_reason = blocked_reason
        if target_status == TaskStatus.READY:
            task.blocked_reason = None
            task.block_kind = None
            task.scheduled_until = None
            if old_status == TaskStatus.BLOCKED:
                task.consecutive_failures = 0
                task.error = ""
            if not await self._store.are_dependencies_met(task_id):
                if force:
                    unsatisfied_deps = await self._store.list_parents(task_id)
                else:
                    parent_ids = await self._store.list_parents(task_id)
                    details: list[UnmetParentInfo] = []
                    for pid in parent_ids:
                        parent = await self._store.get_task(pid)
                        if parent and not parent.is_terminal:
                            details.append(
                                UnmetParentInfo(
                                    task_id=pid,
                                    title=parent.title,
                                    status=parent.status.value,
                                )
                            )
                    raise DependencyUnmetError(
                        task_id,
                        [d["task_id"] for d in details],
                        unmet_details=details,
                    )
        if target_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED):
            task.completed_at = datetime.now(UTC)
        if old_status == TaskStatus.RUNNING and not task.is_terminal:
            task.last_heartbeat_at = None
            task.progress_note = None
        saved = await self._store.save_task(task)

        if old_status == TaskStatus.RUNNING and not saved.is_terminal:
            await self._store.append_event(
                task_id,
                TaskEventKind.RECLAIMED,
                payload={"from": old_status.value, "to": target_status.value},
            )
            runs = await self._store.list_runs(task_id)
            for r in reversed(runs):
                if not r.is_finished:
                    await self._store.complete_run(
                        r.run_id,
                        TaskRunOutcome.RECLAIMED,
                        error="Manual reclaim via move_task",
                    )
                    break

        event_kind = _STATUS_TO_EVENT_KIND.get(saved.status)
        if old_status == TaskStatus.BLOCKED and saved.status == TaskStatus.READY:
            event_kind = TaskEventKind.UNBLOCKED
        if old_status == TaskStatus.RUNNING and not saved.is_terminal:
            event_kind = None
        if event_kind:
            event_payload: dict[str, object] = {
                "from": old_status.value,
                "to": target_status.value,
            }
            if saved.block_kind:
                event_payload["block_kind"] = saved.block_kind.value
            if old_status == TaskStatus.BLOCKED and saved.status == TaskStatus.READY:
                event_payload["source"] = "manual"
            await self._store.append_event(
                task_id,
                event_kind,
                payload=event_payload,
            )
        if unsatisfied_deps:
            await self._store.append_event(
                task_id,
                TaskEventKind.PROMOTED,
                payload={
                    "forced": True,
                    "unsatisfied_deps": unsatisfied_deps,
                    "from": old_status.value,
                },
            )

        if target_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.ARCHIVED):
            await self._promote_dependents(task_id)

        if target_status == TaskStatus.ARCHIVED and saved.branch:
            await self._cleanup_task_worktree(saved)

        if task.board_id in self._dispatchers:
            self._dispatchers[task.board_id].wake()
        _publish_kanban_event(
            saved.board_id,
            task_id,
            "moved",
            title=saved.title,
            detail=saved.result or saved.blocked_reason or saved.error or "",
            status=saved.status.value,
        )
        return saved

    async def cancel_task_execution(self, task_id: str) -> bool:
        """Cancel the asyncio execution of a task without modifying its state.

        Used by cancel_background after move_task(FAILED) to immediately stop
        the running coroutine. Returns True if execution was cancelled.
        """
        task = await self._store.get_task(task_id)
        if task is None:
            return False
        dispatcher = self._dispatchers.get(task.board_id)
        if dispatcher:
            return await dispatcher.cancel_execution(task_id)
        return False

    async def reclaim_task(
        self,
        task_id: str,
        *,
        reason: str | None = None,
        new_agent_id: str | None = None,
    ) -> KanbanTask | None:
        """Manually reclaim a RUNNING task: cancel its worker, reset to READY,
        and optionally reassign to a different agent in one atomic operation.

        Returns the updated task, or None if not found.
        Raises ValueError if the task is not RUNNING.
        """
        task = await self._store.get_task(task_id)
        if task is None:
            return None
        if task.status != TaskStatus.RUNNING:
            raise ValueError(f"Cannot reclaim task in status '{task.status.value}'; only RUNNING tasks can be reclaimed")

        dispatcher = self._dispatchers.get(task.board_id)
        if dispatcher:
            await dispatcher.reclaim_task(task_id, reason)
        else:
            task.status = TaskStatus.READY
            task.consecutive_failures = 0
            task.error = ""
            task.last_heartbeat_at = None
            task.progress_note = None
            await self._store.save_task(task)
            await self._store.append_event(
                task_id,
                TaskEventKind.RECLAIMED,
                payload={"manual": True, "reason": reason or "user request"},
            )

        if new_agent_id is not None:
            if new_agent_id:
                await self._validate_agent_id(new_agent_id)
            task = await self._store.get_task(task_id)
            if task is not None:
                old_agent_id = task.agent_id
                task.agent_id = new_agent_id or None
                await self._store.save_task(task)
                await self._store.append_event(
                    task_id,
                    TaskEventKind.ASSIGNED,
                    payload={
                        "old_agent_id": old_agent_id,
                        "new_agent_id": task.agent_id,
                    },
                )

        task = await self._store.get_task(task_id)
        if task:
            _publish_kanban_event(
                task.board_id,
                task_id,
                "reclaimed",
                title=task.title,
                detail=reason or "user request",
            )
        return task

    async def delete_task(self, task_id: str) -> bool:
        task = await self._store.get_task(task_id)
        board_id = task.board_id if task else ""
        children_ids = await self._store.list_children(task_id)
        deleted = await self._store.delete_task(task_id)
        if deleted and children_ids:
            for child_id in children_ids:
                child = await self._store.get_task(child_id)
                if child is None or child.status != TaskStatus.BACKLOG:
                    continue
                if await self._store.are_dependencies_met(child_id):
                    child.status = TaskStatus.READY
                    await self._store.save_task(child)
                    await self._store.append_event(
                        child_id,
                        TaskEventKind.PROMOTED,
                        payload={"reason": "parent_deleted", "deleted_task_id": task_id},
                    )
                    _publish_kanban_event(child.board_id, child_id, "promoted")
        if deleted and board_id:
            _publish_kanban_event(board_id, task_id, "deleted")
        return deleted

    # -- Dependency management --

    async def add_dependency(
        self,
        child_task_id: str,
        parent_task_id: str,
    ) -> TaskEdge:
        edge = await self._store.add_edge(parent_task_id, child_task_id)
        child = await self._store.get_task(child_task_id)
        if child and child.status == TaskStatus.READY:
            deps_met = await self._store.are_dependencies_met(child_task_id)
            if not deps_met:
                child.status = TaskStatus.BACKLOG
                await self._store.save_task(child)
        if child:
            _publish_kanban_event(child.board_id, child_task_id, "dependency_added")
        return edge

    async def remove_dependency(
        self,
        child_task_id: str,
        parent_task_id: str,
    ) -> bool:
        removed = await self._store.remove_edge(parent_task_id, child_task_id)
        if removed:
            child = await self._store.get_task(child_task_id)
            if child and child.status == TaskStatus.BACKLOG:
                if await self._store.are_dependencies_met(child_task_id):
                    child.status = TaskStatus.READY
                    await self._store.save_task(child)
                    await self._store.append_event(
                        child_task_id,
                        TaskEventKind.PROMOTED,
                        payload={"reason": "dependency_removed"},
                    )
            if child:
                _publish_kanban_event(child.board_id, child_task_id, "dependency_removed")
        return removed

    async def list_task_dependencies(self, task_id: str) -> list[str]:
        return await self._store.list_parents(task_id)

    async def list_task_dependents(self, task_id: str) -> list[str]:
        return await self._store.list_children(task_id)

    async def list_board_edges(self, board_id: str) -> list[TaskEdge]:
        return await self._store.list_board_edges(board_id)

    async def _cleanup_task_worktree(self, task: KanbanTask) -> None:
        """Delegate worktree cleanup to the runner if it supports it."""
        runner = self._runner
        if runner is not None and hasattr(runner, "cleanup_worktree"):
            try:
                await runner.cleanup_worktree(task)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.warning(
                    "Worktree cleanup failed for task %s: %s",
                    task.task_id[:8],
                    exc,
                )

    async def _promote_dependents(self, completed_task_id: str) -> None:
        """Promote BACKLOG children to READY when all dependencies are met."""
        children_ids = await self._store.list_children(completed_task_id)
        for child_id in children_ids:
            child = await self._store.get_task(child_id)
            if child is None or child.status != TaskStatus.BACKLOG:
                continue
            if await self._store.are_dependencies_met(child_id):
                child.status = TaskStatus.READY
                await self._store.save_task(child)
                await self._store.append_event(
                    child_id,
                    TaskEventKind.PROMOTED,
                    payload={"trigger_task_id": completed_task_id},
                )
                _publish_kanban_event(child.board_id, child_id, "promoted")
                logger.info(
                    "Task %s promoted to READY (parent %s completed)",
                    child_id,
                    completed_task_id,
                )

    async def promote_task(
        self,
        task_id: str,
        *,
        force: bool = False,
        reason: str | None = None,
    ) -> PromoteResult:
        """Manually promote a BACKLOG task to READY.

        When force=False and unmet dependencies exist, returns promoted=False
        with the list of unmet parents (lets frontend show a confirmation dialog).
        When force=True, skips dependency check and promotes immediately.
        """
        task = await self._store.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.status != TaskStatus.BACKLOG:
            raise ValueError(f"Only BACKLOG tasks can be promoted, got {task.status.value}")

        parent_ids = await self._store.list_parents(task_id)
        unmet: list[UnmetParentInfo] = []
        for pid in parent_ids:
            parent = await self._store.get_task(pid)
            if parent and not parent.is_terminal:
                unmet.append(
                    UnmetParentInfo(
                        task_id=pid,
                        title=parent.title,
                        status=parent.status.value,
                    )
                )

        if unmet and not force:
            return PromoteResult(promoted=False, forced=False, unmet_parents=unmet)

        task.status = TaskStatus.READY
        task.blocked_reason = None
        await self._store.save_task(task)
        await self._store.append_event(
            task_id,
            TaskEventKind.PROMOTED,
            payload={
                "forced": bool(unmet),
                "reason": reason or "",
                "skipped_parents": [p["task_id"] for p in unmet],
            },
        )
        _publish_kanban_event(task.board_id, task_id, "promoted", title=task.title)
        if task.board_id in self._dispatchers:
            self._dispatchers[task.board_id].wake()
        logger.info(
            "Task %s manually promoted to READY (force=%s, skipped=%d parents)",
            task_id,
            bool(unmet),
            len(unmet),
        )
        return PromoteResult(
            promoted=True,
            forced=bool(unmet),
            reason=reason,
            unmet_parents=unmet,
        )

    @staticmethod
    async def _validate_agent_id(agent_id: str) -> None:
        """Raise ValueError if agent_id does not reference an existing agent profile."""
        from app.services.agent.agent_service import AgentService

        agent = await AgentService.get_agent_by_id(agent_id)
        if agent is None:
            raise ValueError(f"Agent '{agent_id}' not found")

    async def clear_agent_references(self, agent_id: str) -> int:
        """Clear agent_id on all kanban tasks referencing the given agent."""
        return await self._store.clear_agent_references(agent_id)

    # -- Run & Event queries --

    async def list_runs(self, task_id: str) -> list[TaskRun]:
        return await self._store.list_runs(task_id)

    async def list_events(
        self,
        task_id: str,
        *,
        since_id: int | None = None,
    ) -> list[TaskEvent]:
        return await self._store.list_events(task_id, since_id=since_id)

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
        """Return board-level aggregated events with task metadata."""
        return await self._store.list_board_events(
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
        """Add a user comment to a task via the event system."""
        event = await self._store.append_event(
            task_id,
            TaskEventKind.USER_COMMENT,
            payload={"body": body, "author": author},
        )
        task = await self._store.get_task(task_id)
        if task:
            _publish_kanban_event(task.board_id, task_id, "commented")
        return event

    # -- Board summary --

    async def board_summary(self, board_id: str) -> BoardSummaryData | None:
        board = await self._store.get_board(board_id)
        if board is None:
            return None

        status_counts, by_agent, oldest_age = await _gather_summary(
            self._store,
            board_id,
        )

        return BoardSummaryData(
            board=board,
            task_counts=status_counts,
            total_tasks=sum(status_counts.values()),
            dispatcher_active=board_id in self._dispatchers and self._dispatchers[board_id].is_running,
            by_agent=by_agent,
            oldest_ready_age_seconds=oldest_age,
        )

    # -- Boot recovery --

    async def recover_stale_tasks(self) -> int:
        """Reset all RUNNING tasks to READY on server boot.

        Tasks stuck in RUNNING state after a crash/restart are reclaimed
        so the dispatcher can re-dispatch them.  Returns the number reset.
        """
        count = await self._store.reset_stale_running_tasks()
        if count > 0:
            logger.info("[Boot Recovery] Reset %d stale RUNNING tasks to READY", count)
        return count

    # -- Dispatcher lifecycle --

    async def start_dispatcher(
        self,
        board_id: str,
        runner: TaskRunner,
        worker_id: str | None = None,
    ) -> KanbanDispatcher | None:
        """Start a dispatcher for a board."""
        board = await self._store.get_board(board_id)
        if board is None:
            return None

        if board_id in self._dispatchers:
            await self._dispatchers[board_id].stop()

        from app.core.kanban.verifier import KanbanCompletionVerifier

        dispatcher = KanbanDispatcher(
            store=self._store,
            runner=runner,
            board=board,
            worker_id=worker_id,
            verifier=KanbanCompletionVerifier(),
        )
        dispatcher.on_event(
            lambda event_type, task: _publish_kanban_event(
                task.board_id,
                task.task_id,
                event_type,
                title=task.title,
                detail=task.result or task.blocked_reason or task.error or "",
            )
        )
        dispatcher.on_event(_emit_btw_done)
        await dispatcher.start()
        self._dispatchers[board_id] = dispatcher
        logger.info("Started dispatcher for board %s", board_id)
        return dispatcher

    async def stop_dispatcher(self, board_id: str) -> bool:
        if board_id not in self._dispatchers:
            return False
        await self._dispatchers[board_id].stop()
        del self._dispatchers[board_id]
        return True

    async def shutdown(self) -> None:
        """Stop all dispatchers."""
        for board_id in list(self._dispatchers):
            await self.stop_dispatcher(board_id)

    # -- Specifier operations (thin delegations to specify_orchestrator) --

    def _wake_dispatcher(self, board_id: str) -> None:
        if board_id in self._dispatchers:
            self._dispatchers[board_id].wake()

    async def specify_task(
        self,
        task_id: str,
        *,
        persist: bool = False,
        author: str = "specifier",
    ) -> SpecifyOutcome:
        """Preview or apply the TaskSpecifier on a TRIAGE task."""
        return await run_specify_task(
            task_id,
            store=self._store,
            specifier=self._specifier,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            persist=persist,
            author=author,
        )

    async def apply_spec(
        self,
        task_id: str,
        *,
        new_title: str | None,
        new_body: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "specifier",
    ) -> SpecifyOutcome:
        """Persist a cached dry-run spec without re-invoking the LLM."""
        return await run_apply_spec(
            task_id,
            new_title=new_title,
            new_body=new_body,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )

    async def specify_all_triage(
        self,
        board_id: str,
        *,
        persist: bool = False,
        author: str = "specifier",
        max_concurrent: int = SPECIFY_ALL_MAX_CONCURRENT,
    ) -> list[SpecifyOutcome]:
        """Bounded-concurrency sweep over a board's TRIAGE column."""

        async def _delegate(tid: str, p: bool, a: str) -> SpecifyOutcome:
            return await self.specify_task(tid, persist=p, author=a)

        return await run_specify_all_triage(
            board_id,
            store=self._store,
            specify_one=_delegate,
            persist=persist,
            author=author,
            max_concurrent=max_concurrent,
        )

    # -- Decomposer operations (thin delegations to decompose_orchestrator) --

    async def decompose_task(
        self,
        task_id: str,
    ) -> DecomposeOutcome:
        """Preview a decomposition for a TRIAGE task (dry-run only)."""
        return await run_decompose_task(
            task_id,
            store=self._store,
            decomposer=self._decomposer,
        )

    async def apply_decompose(
        self,
        task_id: str,
        *,
        children: list[DecomposeChildSpec],
        rationale: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "decomposer",
    ) -> DecomposeOutcome:
        """Persist children from a cached decompose preview."""

        async def _add_task(
            board_id: str,
            title: str,
            description: str,
            *,
            agent_id: str | None,
            parent_task_id: str | None,
            depends_on: list[str] | None,
            extra_skill_ids: list[str] | None = None,
        ) -> KanbanTask:
            return await self.add_task(
                board_id=board_id,
                title=title,
                description=description,
                agent_id=agent_id,
                parent_task_id=parent_task_id,
                depends_on=depends_on,
                extra_skill_ids=extra_skill_ids,
            )

        return await run_apply_decompose(
            task_id,
            children=children,
            rationale=rationale,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            add_task_fn=_add_task,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )

    async def apply_no_fanout(
        self,
        task_id: str,
        *,
        new_title: str | None = None,
        new_body: str | None = None,
        new_assignee: str | None = None,
        rationale: str = "",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        author: str = "decomposer",
    ) -> DecomposeOutcome:
        """Persist a fanout=false decompose as a Specify (single-task fallback)."""
        return await run_apply_no_fanout(
            task_id,
            new_title=new_title,
            new_body=new_body,
            new_assignee=new_assignee,
            rationale=rationale,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            store=self._store,
            wake_dispatcher=self._wake_dispatcher,
            publish_event=_publish_kanban_event,
            author=author,
        )


async def _gather_summary(
    store: SqlAlchemyKanbanStore,
    board_id: str,
) -> tuple[dict[str, int], dict[str | None, dict[str, int]], int | None]:
    """Fetch status counts, by-agent distribution, and oldest ready age concurrently."""
    status_counts, by_agent, oldest_age = await asyncio.gather(
        store.count_tasks_grouped(board_id),
        store.count_tasks_by_agent(board_id),
        store.oldest_ready_age_seconds(board_id),
    )
    return status_counts, by_agent, oldest_age
