"""A task whose working folder is too broad waits for the user instead of running in it.

[INPUT]
- app.services.kanban.task_runner.worktree.workdir_gate::hold_for_unusable_workdir (POS: run-entry gate on the working folder)
- app.services.kanban.task_runner.runner::KanbanTaskRunner (POS: the production run entry the gate sits in)
- myrm_agent_harness InMemoryKanbanStore

[OUTPUT]
Pins that a task, or a board default, naming a protected or state folder is held before anything is built, and that
an ordinary folder or no folder at all is never held.

[POS]
tests/services/kanban/test_workdir_gate.py
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BlockKind, BoardSettings, KanbanBoard, KanbanTask

from app.services.kanban.task_runner import KanbanTaskRunner
from app.services.kanban.task_runner.worktree.workdir_gate import WORKDIR_TOO_BROAD_REASON, hold_for_unusable_workdir

HOME = str(Path.home())
RUNNER_MODULE = "app.services.kanban.task_runner.runner"


async def _task(store: InMemoryKanbanStore, *, own: str | None = None, board_default: str | None = None) -> KanbanTask:
    await store.save_board(KanbanBoard(board_id="b1", name="Board", settings=BoardSettings(default_workdir=board_default)))
    return await store.save_task(KanbanTask(task_id="t1", board_id="b1", title="Task", workspace_path=own))


@pytest.fixture
def state_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "state"
    folder.mkdir()
    monkeypatch.setattr(
        "app.config.settings.get_settings",
        lambda: SimpleNamespace(database=SimpleNamespace(state_dir=str(folder))),
    )
    return folder


@pytest.mark.parametrize("folder", [HOME, "/"])
async def test_a_task_bound_to_a_protected_container_is_held(folder: str) -> None:
    store = InMemoryKanbanStore()

    held = await hold_for_unusable_workdir(store, await _task(store, own=folder))

    assert held is not None
    assert held.is_blocked
    assert held.block_kind == BlockKind.HUMAN
    assert held.blocked_reason == WORKDIR_TOO_BROAD_REASON


async def test_a_task_that_inherits_a_broad_board_default_is_held() -> None:
    store = InMemoryKanbanStore()

    assert await hold_for_unusable_workdir(store, await _task(store, board_default=HOME)) is not None


async def test_the_state_directory_holds_a_task(state_dir: Path) -> None:
    store = InMemoryKanbanStore()

    assert await hold_for_unusable_workdir(store, await _task(store, own=str(state_dir))) is not None


async def test_the_tasks_own_folder_wins_over_a_broad_board_default(tmp_path: Path) -> None:
    store = InMemoryKanbanStore()

    assert await hold_for_unusable_workdir(store, await _task(store, own=str(tmp_path), board_default=HOME)) is None


async def test_an_ordinary_folder_is_not_held(tmp_path: Path) -> None:
    store = InMemoryKanbanStore()

    assert await hold_for_unusable_workdir(store, await _task(store, own=str(tmp_path))) is None


async def test_a_task_without_any_folder_is_not_held() -> None:
    store = InMemoryKanbanStore()

    assert await hold_for_unusable_workdir(store, await _task(store)) is None


async def test_the_runner_holds_the_task_before_building_anything() -> None:
    store = InMemoryKanbanStore()
    task = await _task(store, own=HOME)

    with patch(f"{RUNNER_MODULE}.build_task_context", new_callable=AsyncMock) as build_context:
        outcome = await KanbanTaskRunner(store).run(task)

    assert not isinstance(outcome, tuple)
    assert outcome.blocked_reason == WORKDIR_TOO_BROAD_REASON
    build_context.assert_not_awaited()
