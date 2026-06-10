"""ChannelBackgroundTaskHandler — business-layer handler for /background slash commands.

Spawns persistent background tasks via the Kanban system for durability,
zombie detection, and restart recovery. Maintains in-memory runtime tokens
(CancellationToken, SteeringToken) for active task control.

[INPUT]
- app.channels.types::InboundMessage (POS: Channel message types)
- app.channels.protocols.background_task (POS: Background task handler protocol)
- app.services.kanban::KanbanService (POS: Kanban business service)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskStatus (POS: Kanban domain types)

[OUTPUT]
- ChannelBackgroundTaskHandler: BackgroundTaskHandler protocol implementation for channel background tasks

[POS]
Business-layer adapter connecting /background (/btw /bg) slash commands to the
persistent Kanban task system. Each background task is created as a KanbanTask,
gaining automatic persistence (SQLAlchemy), restart recovery, zombie detection,
heartbeat monitoring, and auto-retry — all provided by KanbanDispatcher.
Runtime steering and cancellation use in-memory tokens tied to the executing task.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.protocols.background_task import (
    BackgroundTaskInfo,
)
from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = 5

_SYSTEM_BOARD_NAME = "__background_tasks__"
_SYSTEM_BOARD_DESCRIPTION = "System board for /btw background tasks"


@dataclass
class _RuntimeTokens:
    """In-memory runtime tokens for an active background task."""

    cancel_token: CancellationToken = field(default_factory=CancellationToken)
    steering_token: SteeringToken = field(default_factory=SteeringToken)
    created_at: float = field(default_factory=time.time)


class ChannelBackgroundTaskHandler:
    """BackgroundTaskHandler implementation backed by the persistent Kanban system.

    Tasks are persisted as KanbanTasks, gaining zombie detection, restart
    recovery, and auto-retry. In-memory runtime tokens allow cancel/steer
    of currently executing tasks.
    """

    def __init__(self) -> None:
        self._runtime_tokens: dict[str, _RuntimeTokens] = {}
        self._system_board_id: str | None = None

    async def _ensure_system_board(self) -> str:
        """Get or create the system background tasks board."""
        if self._system_board_id is not None:
            return self._system_board_id

        from myrm_agent_harness.toolkits.kanban.types import BoardSettings

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        boards = await svc.list_boards()
        for board in boards:
            if board.name == _SYSTEM_BOARD_NAME:
                self._system_board_id = board.board_id
                return board.board_id

        board = await svc.create_board(
            name=_SYSTEM_BOARD_NAME,
            description=_SYSTEM_BOARD_DESCRIPTION,
            settings=BoardSettings(
                zombie_timeout_seconds=300,
                auto_block_after_consecutive_failures=2,
            ),
        )
        self._system_board_id = board.board_id
        return board.board_id

    async def spawn_background(
        self,
        msg: InboundMessage,
        prompt: str,
    ) -> str:
        """Spawn a new background task as a persistent KanbanTask."""
        from myrm_agent_harness.toolkits.kanban.types import TaskPriority, TaskStatus

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        board_id = await self._ensure_system_board()

        running_count = await self._count_running(board_id)
        if running_count >= MAX_CONCURRENT_TASKS:
            raise RuntimeError(
                f"Maximum concurrent background tasks reached ({MAX_CONCURRENT_TASKS}). "
                "Please wait for existing tasks to complete or cancel one."
            )

        chat_id = msg.chat_id or msg.sender_id
        user_id = msg.user_id or ""

        task = await svc.add_task(
            board_id=board_id,
            title=prompt[:100],
            description=prompt,
            priority=TaskPriority.NORMAL,
            initial_status=TaskStatus.READY,
            agent_id=None,
        )

        task.metadata = task.metadata or {}
        task.metadata["background_source"] = "btw"
        task.metadata["channel"] = msg.channel
        task.metadata["chat_id"] = chat_id
        task.metadata["user_id"] = user_id
        task.metadata["thread_id"] = msg.thread_id
        meta = msg.metadata or {}
        task.metadata["locale"] = meta.get("locale") or meta.get("platform_locale") or "en"
        await svc.store.save_task(task)

        logger.info(
            "Background task %s spawned via Kanban for %s/%s: %s",
            task.task_id,
            msg.channel,
            chat_id,
            prompt[:80],
        )
        return task.task_id

    async def cancel_background(
        self,
        msg: InboundMessage,
        task_id: str,
    ) -> bool:
        """Cancel a running or queued background task."""
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        task = await svc.store.get_task(task_id)
        if not task or task.status not in (TaskStatus.RUNNING, TaskStatus.READY):
            return False

        tokens = self._runtime_tokens.get(task_id)
        if tokens:
            tokens.cancel_token.cancel("user_cancelled")

        await svc.move_task(task_id, TaskStatus.FAILED, error="Cancelled by user")
        await svc.cancel_task_execution(task_id)
        self._runtime_tokens.pop(task_id, None)
        logger.info("Background task %s cancelled", task_id)
        return True

    async def list_background(
        self,
        msg: InboundMessage,
    ) -> list[BackgroundTaskInfo]:
        """List all background tasks for the current user."""
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()

        if self._system_board_id is None:
            await self._ensure_system_board()
        board_id = self._system_board_id
        if board_id is None:
            return []

        tasks = await svc.store.list_tasks(board_id)
        user_id = msg.user_id or msg.sender_id
        chat_id = msg.chat_id or msg.sender_id

        results: list[BackgroundTaskInfo] = []
        for task in tasks:
            meta = task.metadata or {}
            task_user = meta.get("user_id", "")
            task_chat = meta.get("chat_id", "")
            if task_user != user_id and task_chat != chat_id:
                continue

            status = _kanban_status_to_bg_status(task.status)
            completed_at = task.completed_at.timestamp() if task.completed_at else None
            created_at = task.created_at.timestamp() if task.created_at else time.time()

            result_text: str | None = None
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                events = await svc.store.list_events(task.task_id)
                for ev in reversed(events):
                    if ev.payload and ev.payload.get("result_preview"):
                        result_text = str(ev.payload["result_preview"])[:100]
                        break

            results.append(
                BackgroundTaskInfo(
                    task_id=task.task_id,
                    prompt=task.description or task.title,
                    status=status,
                    created_at=created_at,
                    completed_at=completed_at,
                    result_preview=result_text,
                )
            )

        return sorted(results, key=lambda x: x.created_at, reverse=True)

    async def steer_background(
        self,
        msg: InboundMessage,
        task_id: str,
        instruction: str,
    ) -> bool:
        """Inject a steering instruction into a running background task."""
        tokens = self._runtime_tokens.get(task_id)
        if not tokens:
            return False
        tokens.steering_token.steer(instruction)
        return True

    def register_runtime_tokens(
        self,
        task_id: str,
        cancel_token: CancellationToken,
        steering_token: SteeringToken,
    ) -> None:
        """Register runtime tokens for an active task (called by KanbanTaskRunner)."""
        self._runtime_tokens[task_id] = _RuntimeTokens(
            cancel_token=cancel_token,
            steering_token=steering_token,
        )

    def unregister_runtime_tokens(self, task_id: str) -> None:
        """Unregister runtime tokens when a task completes."""
        self._runtime_tokens.pop(task_id, None)

    async def _count_running(self, board_id: str) -> int:
        """Count currently running tasks on the system board."""
        from myrm_agent_harness.toolkits.kanban.types import TaskStatus

        from app.services.kanban import KanbanService

        svc = KanbanService.get_instance()
        tasks = await svc.store.list_tasks(board_id)
        return sum(1 for t in tasks if t.status == TaskStatus.RUNNING)


def _kanban_status_to_bg_status(status: str) -> str:
    """Map KanbanTask TaskStatus value to background task status string."""
    from myrm_agent_harness.toolkits.kanban.types import TaskStatus

    status_map = {
        TaskStatus.READY: "running",
        TaskStatus.RUNNING: "running",
        TaskStatus.COMPLETED: "completed",
        TaskStatus.FAILED: "failed",
        TaskStatus.BLOCKED: "failed",
        TaskStatus.BACKLOG: "running",
        TaskStatus.TRIAGE: "running",
        TaskStatus.ARCHIVED: "completed",
    }
    return status_map.get(status, "running")  # type: ignore[arg-type]
