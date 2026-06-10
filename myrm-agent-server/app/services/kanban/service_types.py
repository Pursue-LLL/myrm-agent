"""Kanban service shared types and status-mapping constants."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TypedDict

from myrm_agent_harness.toolkits.kanban.types import (
    KanbanBoard,
    TaskEventKind,
    TaskRunOutcome,
    TaskStatus,
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


class Sentinel(enum.Enum):
    """Distinguishes 'not provided' from explicit None (clear agent_id)."""

    UNSET = "UNSET"


UNSET = Sentinel.UNSET


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


STATUS_TO_EVENT_KIND: dict[TaskStatus, TaskEventKind] = {
    TaskStatus.BLOCKED: TaskEventKind.BLOCKED,
    TaskStatus.ARCHIVED: TaskEventKind.ARCHIVED,
    TaskStatus.COMPLETED: TaskEventKind.COMPLETED,
    TaskStatus.FAILED: TaskEventKind.FAILED,
}

SYNTHETIC_RUN_TARGETS: frozenset[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.BLOCKED, TaskStatus.FAILED}
)

TARGET_TO_RUN_OUTCOME: dict[TaskStatus, TaskRunOutcome] = {
    TaskStatus.COMPLETED: TaskRunOutcome.COMPLETED,
    TaskStatus.BLOCKED: TaskRunOutcome.BLOCKED,
    TaskStatus.FAILED: TaskRunOutcome.CRASHED,
}
