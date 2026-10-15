"""The run-entry gate against the SQLite-backed store the product runs on.

[INPUT]
- app.core.kanban.adapters.sqlalchemy_store::SqlAlchemyKanbanStore (POS: the production KanbanStore; events ordered by id, JSON task metadata)
- app.services.kanban.task_runner.worktree.landing_gate::hold_for_unlanded_parents (POS: run-entry gate on parents' failed merges)

[OUTPUT]
Pins that the gate's reading of a parent's event stream (newest failure after the latest completion) and its stored
acknowledgement behave the same on the real schema as on the in-memory store.

[POS]
tests/core/kanban/test_landing_gate_sql_store.py
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask, TaskEventKind, TaskStatus

from app.core.kanban.adapters.sqlalchemy_store import SqlAlchemyKanbanStore
from app.services.kanban.task_runner.worktree.landing_gate import (
    ACKNOWLEDGED_MERGE_FAILURE_KEY,
    hold_for_unlanded_parents,
)

# The gate only compares the parent's and the child's repository, so the directory does not have to exist.
_REPO = "/nonexistent/landing-gate-repo"


def _task(board_id: str, status: TaskStatus) -> KanbanTask:
    return KanbanTask(
        task_id=f"task-{uuid.uuid4().hex}",
        board_id=board_id,
        title="Gate",
        status=status,
        branch="main",
        workspace_path=_REPO,
    )


@pytest_asyncio.fixture
async def board() -> AsyncIterator[tuple[SqlAlchemyKanbanStore, str]]:
    store = SqlAlchemyKanbanStore()
    saved = await store.save_board(KanbanBoard(board_id=f"board-{uuid.uuid4().hex}", name="Landing gate"))
    yield store, saved.board_id
    await store.delete_board(saved.board_id)


@pytest.mark.asyncio
async def test_a_failure_holds_once_and_a_newer_failure_holds_again(board: tuple[SqlAlchemyKanbanStore, str]) -> None:
    store, board_id = board
    parent = await store.save_task(_task(board_id, TaskStatus.COMPLETED))
    child = await store.save_task(_task(board_id, TaskStatus.READY))
    await store.add_edge(parent.task_id, child.task_id)
    await store.append_event(parent.task_id, TaskEventKind.COMPLETED)
    failure = await store.append_event(parent.task_id, TaskEventKind.MERGE_CONFLICT, payload={"conflicts": ["a.py"]})

    held = await hold_for_unlanded_parents(store, child)
    assert held is not None
    assert held.metadata_patch == {ACKNOWLEDGED_MERGE_FAILURE_KEY: failure.event_id}

    child.metadata = {**child.metadata, **(held.metadata_patch or {})}
    await store.save_task(child)
    acknowledged = await store.get_task(child.task_id)
    assert acknowledged is not None
    assert await hold_for_unlanded_parents(store, acknowledged) is None

    # A completion after the failure means the parent's code landed since, so even a dependent that never saw the
    # failure is not held.
    await store.append_event(parent.task_id, TaskEventKind.COMPLETED)
    bystander = await store.save_task(_task(board_id, TaskStatus.READY))
    await store.add_edge(parent.task_id, bystander.task_id)
    assert await hold_for_unlanded_parents(store, bystander) is None

    newer = await store.append_event(parent.task_id, TaskEventKind.MERGE_CONFLICT)
    again = await hold_for_unlanded_parents(store, acknowledged)
    assert again is not None
    assert again.metadata_patch == {ACKNOWLEDGED_MERGE_FAILURE_KEY: newer.event_id}
