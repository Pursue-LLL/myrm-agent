"""Kanban race orchestration: parallel lanes for one task, human picks winner.

[INPUT]
- app.services.kanban.service_mixins (POS: KanbanService facade — add/move/
  approve/list tasks, board settings.)
- myrm_agent_harness.toolkits.kanban.types (POS: KanbanTask/TaskStatus/
  TaskEventKind domain types.)

[OUTPUT]
- RaceError, LaneSpec, RaceEstimate, estimate_race_cost, start_race,
  get_race_lanes, pick_race_winner (idempotent via RACE_DECIDED lookup).
- Lane diff review (LaneFileChange, get_lane_changes, get_lane_file_contents)
  re-exported from race_lane_diff.py.

[POS]
Business-layer race flow. A race fans one task out into N child lane tasks
(grouped by ``parent_task_id``, each bound to its own agent profile), waits
for lanes to reach IN_REVIEW, then merges the human-picked winner through the
existing approve/merge path and archives the losers (worktree cleanup keeps
dirty edits; loser branches are preserved, never force-deleted).

Deliberately adds no harness machinery: parallelism comes from the existing
dispatcher ``max_concurrent_tasks`` slots, isolation from per-task worktrees,
and gating from IN_REVIEW approve/reject. V1 targets git-worktree tasks;
like any other branched task, lanes resolve their worktree at dispatch time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskRun,
    TaskStatus,
)

if TYPE_CHECKING:
    from app.services.kanban.service import KanbanService

logger = logging.getLogger(__name__)

MIN_LANES = 2
MAX_LANES = 5
DEFAULT_LANES = 3
# Interim per-lane token estimate when the board has no completed-task
# history yet. Superseded by the dedicated quota service (roadmap 260).
FALLBACK_TOKENS_PER_LANE = 30_000


class RaceError(ValueError):
    """Raised when a race cannot start or finish. ``code`` is machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LaneSpec:
    """One race contestant. All fields optional — unset inherits the parent."""

    agent_id: str | None = None
    model_override: str | None = None
    instruction_variant: str = ""
    title_suffix: str = ""


@dataclass(frozen=True)
class RaceEstimate:
    """Cost preview shown before the human confirms a race."""

    lanes: int
    per_lane_avg_tokens: int
    total_tokens: int
    based_on_completed_tasks: int

    def to_dict(self) -> dict[str, int]:
        return {
            "lanes": self.lanes,
            "per_lane_avg_tokens": self.per_lane_avg_tokens,
            "total_tokens": self.total_tokens,
            "based_on_completed_tasks": self.based_on_completed_tasks,
        }


def _run_tokens(run: TaskRun) -> int:
    usage = run.token_usage or {}
    return sum(v for v in usage.values() if isinstance(v, int) and v > 0)


async def estimate_race_cost(svc: KanbanService, board_id: str, lanes: int) -> RaceEstimate:
    """Estimate token cost from recent completed-task runs on the board."""
    completed = await svc.list_tasks(board_id, status=TaskStatus.COMPLETED)
    samples: list[int] = []
    for task in completed[-10:]:
        try:
            runs = await svc.list_runs(task.task_id)
        except Exception:
            continue
        total = sum(_run_tokens(run) for run in runs)
        if total > 0:
            samples.append(total)
    per_lane = sum(samples) // len(samples) if samples else FALLBACK_TOKENS_PER_LANE
    return RaceEstimate(
        lanes=lanes,
        per_lane_avg_tokens=per_lane,
        total_tokens=per_lane * lanes,
        based_on_completed_tasks=len(samples),
    )


async def _get_race_parent(svc: KanbanService, task_id: str) -> KanbanTask:
    task = await svc.get_task(task_id)
    if task is None:
        raise RaceError("unknown_task", f"Task {task_id} not found")
    return task


async def start_race(
    svc: KanbanService,
    board_id: str,
    parent_task_id: str,
    lane_specs: list[LaneSpec],
    *,
    branch: str | None = None,
    confirm_cost: bool = False,
) -> dict[str, Any]:
    """Fan one task out into N parallel lane children.

    The parent stays a branchless BACKLOG shell; each lane inherits the race
    target branch and requires approval, so finished lanes park in IN_REVIEW
    for human judging. Returns the parent id, lane ids and cost estimate.
    """
    parent = await _get_race_parent(svc, parent_task_id)
    if parent.board_id != board_id:
        raise RaceError("wrong_board", "Parent task is not on this board")
    if parent.is_terminal:
        raise RaceError("race_parent_not_ready", "Races start from backlog or ready tasks")
    if parent.status not in (TaskStatus.BACKLOG, TaskStatus.READY):
        raise RaceError("race_parent_not_ready", "Races start from backlog or ready tasks")
    target_branch = branch or parent.branch
    if not target_branch:
        raise RaceError(
            "race_requires_branch",
            "Racing needs git isolation: set a branch on the task first",
        )
    n = len(lane_specs)
    if not MIN_LANES <= n <= MAX_LANES:
        raise RaceError(
            "bad_lane_count",
            f"Race needs {MIN_LANES}-{MAX_LANES} lanes, got {n}",
        )
    board = await svc.get_board(board_id)
    if board is None:
        raise RaceError("unknown_board", f"Board {board_id} not found")
    slots = board.settings.max_concurrent_tasks
    if slots < n:
        raise RaceError(
            "insufficient_slots",
            f"Board runs {slots} tasks at once but the race needs {n}; "
            "raise max_concurrent_tasks in board settings first",
        )
    existing = await svc.store.list_tasks(board_id, parent_task_id=parent.task_id)
    if any(not t.is_terminal for t in existing):
        raise RaceError("race_in_progress", "This task already has a live race")
    if not confirm_cost:
        raise RaceError("cost_confirmation_required", "Confirm the cost estimate")
    estimate = await estimate_race_cost(svc, board_id, n)

    letters = "ABCDE"
    lane_ids: list[str] = []
    criteria: str | list[dict[str, str | int]] | None = None
    raw_criteria = parent.metadata.get("completion_criteria")
    if isinstance(raw_criteria, str):
        criteria = raw_criteria
    elif isinstance(raw_criteria, list) and all(
        isinstance(item, dict) for item in raw_criteria
    ):
        criteria = cast("list[dict[str, str | int]]", raw_criteria)
    for i, spec in enumerate(lane_specs):
        suffix = spec.title_suffix or f"方案{letters[i]}"
        description = parent.description
        if spec.instruction_variant:
            description = f"{description}\n\n【赛马变体】{spec.instruction_variant}"
        try:
            lane = await svc.add_task(
                board_id,
                title=f"{parent.title}（{suffix}）",
                description=description,
                priority=parent.priority,
                parent_task_id=parent.task_id,
                agent_id=spec.agent_id or parent.agent_id,
                model_override=spec.model_override or parent.model_override,
                max_retries=parent.max_retries,
                extra_skill_ids=list(parent.extra_skill_ids) or None,
                completion_criteria=criteria,
                max_runtime_seconds=parent.max_runtime_seconds,
                branch=target_branch,
                goal_mode=False,
                require_approval=True,
                metadata_patch={"race_parent": parent.task_id, "race_lane": i},
            )
        except Exception:
            # A half-built race blocks retries via race_in_progress; archive
            # what was created so the next attempt starts clean. Best effort:
            # archive failures must not mask the original error.
            for created_id in lane_ids:
                try:
                    await svc.move_task(created_id, TaskStatus.ARCHIVED)
                except Exception:
                    logger.warning(
                        "Race rollback archive failed for lane %s", created_id[:8]
                    )
            raise
        lane_ids.append(lane.task_id)

    await svc.store.append_event(
        parent.task_id,
        TaskEventKind.RACE_STARTED,
        payload={
            "lane_count": n,
            "lane_ids": lane_ids,
            "branch": target_branch,
            "estimated_total_tokens": estimate.total_tokens,
        },
    )
    return {
        "parent_task_id": parent.task_id,
        "lane_ids": lane_ids,
        "estimate": estimate.to_dict(),
    }
async def _find_decision(
    svc: KanbanService, parent_task_id: str
) -> dict[str, Any] | None:
    """Return the stored decide outcome when this race was already decided."""
    try:
        events = await svc.list_events(parent_task_id)
    except Exception:
        return None
    for event in reversed(events):
        if event.kind == TaskEventKind.RACE_DECIDED and event.payload:
            winner_id = event.payload.get("winner_task_id")
            archived = event.payload.get("archived_lane_ids")
            if isinstance(winner_id, str) and isinstance(archived, list):
                return {
                    "parent_task_id": parent_task_id,
                    "winner_task_id": winner_id,
                    "archived_lane_ids": [i for i in archived if isinstance(i, str)],
                }
    return None


async def get_race_lanes(
    svc: KanbanService, board_id: str, parent_task_id: str
) -> list[KanbanTask]:
    """List live and finished lanes of a race parent, oldest first."""
    parent = await _get_race_parent(svc, parent_task_id)
    lanes = await svc.store.list_tasks(board_id, parent_task_id=parent.task_id)
    return [t for t in lanes if t.metadata.get("race_parent") == parent.task_id]


async def pick_race_winner(
    svc: KanbanService,
    parent_task_id: str,
    winner_task_id: str,
    *,
    approver: str | None = None,
) -> dict[str, Any]:
    """Merge the human-picked winner, archive the losers, close the parent.

    The winner goes through the standard approve path (COMPLETED + worktree
    merge). Losers move to ARCHIVED (worktree cleanup keeps dirty edits;
    their branches are preserved). The branchless parent completes with no
    git side effects.
    """
    parent = await _get_race_parent(svc, parent_task_id)
    decided = await _find_decision(svc, parent.task_id)
    if decided is not None:
        # Idempotent retry: a previous decide already merged the winner.
        return decided
    lanes = await get_race_lanes(svc, parent.board_id, parent.task_id)
    lane_ids = {t.task_id for t in lanes}
    if winner_task_id not in lane_ids:
        raise RaceError("not_a_lane", "Winner decision must be one of the race lanes")
    winner = await svc.get_task(winner_task_id)
    if winner is None or winner.status != TaskStatus.IN_REVIEW:
        raise RaceError(
            "winner_not_reviewable",
            "Winner must be waiting for review (IN_REVIEW)",
        )
    await svc.approve_task(winner_task_id, approver=approver)
    archived: list[str] = []
    for lane in lanes:
        if lane.task_id == winner_task_id or lane.is_terminal:
            continue
        await svc.move_task(lane.task_id, TaskStatus.ARCHIVED)
        archived.append(lane.task_id)
    if not parent.is_terminal:
        await svc.move_task(parent.task_id, TaskStatus.COMPLETED)
    await svc.store.append_event(
        parent.task_id,
        TaskEventKind.RACE_DECIDED,
        payload={"winner_task_id": winner_task_id, "archived_lane_ids": archived},
    )
    return {
        "parent_task_id": parent.task_id,
        "winner_task_id": winner_task_id,
        "archived_lane_ids": archived,
    }


# Lane diff review lives in race_lane_diff.py (split for file-line budget);
# re-exported here so existing imports keep working.
from app.services.kanban.race_lane_diff import (  # noqa: E402
    LaneFileChange,
    get_lane_changes,
    get_lane_file_contents,
)

__all__ = [
    "RaceError",
    "LaneSpec",
    "RaceEstimate",
    "LaneFileChange",
    "estimate_race_cost",
    "start_race",
    "get_race_lanes",
    "pick_race_winner",
    "get_lane_changes",
    "get_lane_file_contents",
]
