"""Tests for race orchestration (one task -> N lane children -> pick winner).

Covers: start validation (branch/slots/count/confirm/live race), lane
creation linkage, cost estimate fallback/history, and winner decision flow.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.race_orchestrator import (
    LaneSpec,
    RaceError,
    estimate_race_cost,
    get_race_lanes,
    pick_race_winner,
    start_race,
)


def _parent(**overrides: object) -> KanbanTask:
    kwargs: dict[str, object] = {
        "task_id": "parent-1",
        "board_id": "board-1",
        "title": "Fix retry",
        "description": "Make it idempotent",
        "status": TaskStatus.BACKLOG,
        "branch": "feature/retry",
    }
    kwargs.update(overrides)
    return KanbanTask(**kwargs)  # type: ignore[arg-type]


def _lane(task_id: str, status: TaskStatus) -> KanbanTask:
    return KanbanTask(
        task_id=task_id,
        board_id="board-1",
        title=f"Fix retry ({task_id})",
        status=status,
        branch="feature/retry",
        parent_task_id="parent-1",
        metadata={"race_parent": "parent-1", "race_lane": 0},
    )


def _make_svc(task: KanbanTask | None, *, slots: int = 3) -> AsyncMock:
    svc = AsyncMock()
    svc.get_task.return_value = task
    svc.get_board.return_value = SimpleNamespace(
        settings=SimpleNamespace(max_concurrent_tasks=slots)
    )
    svc.store.list_tasks.return_value = []
    svc.list_tasks.return_value = []
    return svc


@pytest.mark.asyncio
async def test_start_rejects_unknown_task() -> None:
    svc = _make_svc(None)
    with pytest.raises(RaceError) as exc:
        await start_race(svc, "board-1", "missing", [LaneSpec(), LaneSpec()])
    assert exc.value.code == "unknown_task"


@pytest.mark.asyncio
async def test_start_rejects_missing_branch() -> None:
    svc = _make_svc(_parent(branch=None))
    with pytest.raises(RaceError) as exc:
        await start_race(
            svc, "board-1", "parent-1", [LaneSpec(), LaneSpec()], confirm_cost=True
        )
    assert exc.value.code == "race_requires_branch"


@pytest.mark.asyncio
async def test_start_rejects_bad_lane_count() -> None:
    svc = _make_svc(_parent())
    with pytest.raises(RaceError) as exc:
        await start_race(svc, "board-1", "parent-1", [LaneSpec()], confirm_cost=True)
    assert exc.value.code == "bad_lane_count"


@pytest.mark.asyncio
async def test_start_rejects_insufficient_slots() -> None:
    svc = _make_svc(_parent(), slots=2)
    with pytest.raises(RaceError) as exc:
        await start_race(
            svc,
            "board-1",
            "parent-1",
            [LaneSpec(), LaneSpec(), LaneSpec()],
            confirm_cost=True,
        )
    assert exc.value.code == "insufficient_slots"


@pytest.mark.asyncio
async def test_start_requires_cost_confirmation() -> None:
    svc = _make_svc(_parent())
    with pytest.raises(RaceError) as exc:
        await start_race(svc, "board-1", "parent-1", [LaneSpec(), LaneSpec()])
    assert exc.value.code == "cost_confirmation_required"
    svc.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_start_rejects_live_race() -> None:
    svc = _make_svc(_parent())
    svc.store.list_tasks.return_value = [_lane("lane-1", TaskStatus.RUNNING)]
    with pytest.raises(RaceError) as exc:
        await start_race(
            svc, "board-1", "parent-1", [LaneSpec(), LaneSpec()], confirm_cost=True
        )
    assert exc.value.code == "race_in_progress"


@pytest.mark.asyncio
async def test_start_rejects_terminal_parent() -> None:
    svc = _make_svc(_parent(status=TaskStatus.COMPLETED))
    with pytest.raises(RaceError) as exc:
        await start_race(
            svc, "board-1", "parent-1", [LaneSpec(), LaneSpec()], confirm_cost=True
        )
    assert exc.value.code == "race_parent_not_ready"
    svc.add_task.assert_not_called()


@pytest.mark.asyncio
async def test_start_rolls_back_half_built_race() -> None:
    svc = _make_svc(_parent())

    async def add_task(board_id: str, title: str, **kwargs: object) -> KanbanTask:
        if "方案B" in title:
            raise RuntimeError("boom")
        return _lane("lane-0", TaskStatus.READY)

    svc.add_task.side_effect = add_task
    with pytest.raises(RuntimeError):
        await start_race(
            svc, "board-1", "parent-1", [LaneSpec(), LaneSpec()], confirm_cost=True
        )
    svc.move_task.assert_awaited_once_with("lane-0", TaskStatus.ARCHIVED)


@pytest.mark.asyncio
async def test_pick_winner_is_idempotent_after_decision() -> None:
    from myrm_agent_harness.toolkits.kanban.types import TaskEventKind

    parent = _parent()
    svc = _make_svc(parent)
    svc.list_events.return_value = [
        SimpleNamespace(
            kind=TaskEventKind.RACE_DECIDED,
            payload={"winner_task_id": "lane-w", "archived_lane_ids": ["lane-l"]},
        )
    ]
    outcome = await pick_race_winner(svc, "parent-1", "lane-w")
    assert outcome == {
        "parent_task_id": "parent-1",
        "winner_task_id": "lane-w",
        "archived_lane_ids": ["lane-l"],
    }
    svc.approve_task.assert_not_called()
    svc.move_task.assert_not_called()


@pytest.mark.asyncio
async def test_start_creates_linked_lanes() -> None:
    svc = _make_svc(_parent(agent_id="agent-main"))
    created: list[KanbanTask] = []

    async def add_task(board_id: str, title: str, **kwargs: object) -> KanbanTask:
        lane = _lane(f"lane-{len(created)}", TaskStatus.READY)
        lane.title = title
        created.append(lane)
        add_task_kwargs.append(kwargs)
        return lane

    add_task_kwargs: list[dict[str, object]] = []
    svc.add_task.side_effect = add_task
    outcome = await start_race(
        svc,
        "board-1",
        "parent-1",
        [LaneSpec(agent_id="agent-a"), LaneSpec(instruction_variant="be bold")],
        confirm_cost=True,
    )
    assert outcome["parent_task_id"] == "parent-1"
    assert len(outcome["lane_ids"]) == 2
    first_kwargs = add_task_kwargs[0]
    assert first_kwargs["parent_task_id"] == "parent-1"
    assert first_kwargs["agent_id"] == "agent-a"
    assert first_kwargs["branch"] == "feature/retry"
    assert first_kwargs["require_approval"] is True
    assert "be bold" in add_task_kwargs[1]["description"]
    assert outcome["estimate"]["lanes"] == 2


@pytest.mark.asyncio
async def test_estimate_falls_back_without_history() -> None:
    svc = _make_svc(_parent())
    svc.list_runs.return_value = []
    estimate = await estimate_race_cost(svc, "board-1", 3)
    assert estimate.total_tokens == estimate.per_lane_avg_tokens * 3
    assert estimate.based_on_completed_tasks == 0


@pytest.mark.asyncio
async def test_estimate_uses_completed_history() -> None:
    from datetime import datetime

    from myrm_agent_harness.toolkits.kanban.types import UTC, TaskRun

    svc = _make_svc(_parent())
    done = _parent(task_id="done-1")
    svc.list_tasks.return_value = [done]
    svc.list_runs.return_value = [
        TaskRun(
            run_id="r1",
            task_id="done-1",
            worker_id="w",
            started_at=datetime.now(UTC),
            token_usage={"total": 1000},
        )
    ]
    estimate = await estimate_race_cost(svc, "board-1", 2)
    assert estimate.per_lane_avg_tokens == 1000
    assert estimate.based_on_completed_tasks == 1


@pytest.mark.asyncio
async def test_pick_winner_merges_and_archives() -> None:
    parent = _parent()
    winner = _lane("lane-w", TaskStatus.IN_REVIEW)
    loser = _lane("lane-l", TaskStatus.IN_REVIEW)
    svc = _make_svc(parent)
    svc.get_task.side_effect = lambda task_id: {
        "parent-1": parent,
        "lane-w": winner,
    }.get(task_id)
    svc.store.list_tasks.return_value = [winner, loser]
    outcome = await pick_race_winner(svc, "parent-1", "lane-w", approver="human")
    assert outcome["winner_task_id"] == "lane-w"
    assert outcome["archived_lane_ids"] == ["lane-l"]
    svc.approve_task.assert_awaited_once_with("lane-w", approver="human")
    svc.move_task.assert_any_call("lane-l", TaskStatus.ARCHIVED)
    svc.move_task.assert_any_call("parent-1", TaskStatus.COMPLETED)


@pytest.mark.asyncio
async def test_pick_winner_rejects_non_lane() -> None:
    svc = _make_svc(_parent())
    svc.store.list_tasks.return_value = [_lane("lane-w", TaskStatus.IN_REVIEW)]
    with pytest.raises(RaceError) as exc:
        await pick_race_winner(svc, "parent-1", "outsider")
    assert exc.value.code == "not_a_lane"


@pytest.mark.asyncio
async def test_pick_winner_requires_reviewable_lane() -> None:
    parent = _parent()
    running = _lane("lane-w", TaskStatus.RUNNING)
    svc = _make_svc(parent)
    svc.get_task.side_effect = lambda task_id: {
        "parent-1": parent,
        "lane-w": running,
    }.get(task_id)
    svc.store.list_tasks.return_value = [running]
    with pytest.raises(RaceError) as exc:
        await pick_race_winner(svc, "parent-1", "lane-w")
    assert exc.value.code == "winner_not_reviewable"


@pytest.mark.asyncio
async def test_lane_changes_parses_numstat() -> None:
    from unittest.mock import patch

    from app.services.kanban.race_orchestrator import get_lane_changes

    parent = _parent()
    lane = _lane("lane-1", TaskStatus.RUNNING)
    lane.workspace_path = "/repo"
    svc = _make_svc(parent)
    svc.get_task.side_effect = lambda task_id: {
        "parent-1": parent,
        "lane-1": lane,
    }.get(task_id)

    async def fake_git(base_dir: str, args: list[str], timeout: int = 15):
        assert base_dir == "/repo"
        return SimpleNamespace(returncode=0, stdout="10\t2\tsrc/a.py\n0\t0\t../evil.py\n")

    with patch(
        "app.services.kanban.race_orchestrator._run_git", side_effect=fake_git
    ):
        outcome = await get_lane_changes(svc, "board-1", "parent-1", "lane-1")
    assert outcome["lane_task_id"] == "lane-1"
    assert outcome["files"] == [{"path": "src/a.py", "additions": 10, "deletions": 2}]


@pytest.mark.asyncio
async def test_lane_file_rejects_unsafe_path() -> None:
    from app.services.kanban.race_orchestrator import get_lane_file_contents

    svc = _make_svc(_parent())
    with pytest.raises(RaceError) as exc:
        await get_lane_file_contents(svc, "board-1", "parent-1", "lane-1", "../evil.py")
    assert exc.value.code == "unsafe_path"


@pytest.mark.asyncio
async def test_lane_changes_rejects_foreign_lane() -> None:
    from app.services.kanban.race_orchestrator import get_lane_changes

    svc = _make_svc(_parent())
    svc.get_task.side_effect = lambda task_id: {
        "parent-1": _parent(),
        "other": _parent(task_id="other"),
    }.get(task_id)
    with pytest.raises(RaceError) as exc:
        await get_lane_changes(svc, "board-1", "parent-1", "other")
    assert exc.value.code == "not_a_lane"


@pytest.mark.asyncio
async def test_get_race_lanes_filters_race_children() -> None:
    svc = _make_svc(_parent())
    lane = _lane("lane-w", TaskStatus.IN_REVIEW)
    other = _parent(task_id="other")
    other.parent_task_id = "parent-1"
    svc.store.list_tasks.return_value = [lane, other]
    lanes = await get_race_lanes(svc, "board-1", "parent-1")
    assert [t.task_id for t in lanes] == ["lane-w"]
