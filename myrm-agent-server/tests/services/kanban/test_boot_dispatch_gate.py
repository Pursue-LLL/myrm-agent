"""Boot gate: a server with no usable model configuration must not claim queued tasks.

A 390-task board used to produce 390 failure rows, ~760 tracebacks and 1505 `database is locked`
errors on every boot, plus ~8-10 s of startup time, because every dispatcher claimed its READY
tasks immediately and each claim failed for the same reason. These tests pin the gate.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from myrm_agent_harness.api import ConfigIncompleteError
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    BoardSettings,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.services.kanban import dispatch_gate
from app.services.kanban.dispatcher_lifecycle import shutdown_dispatchers, start_dispatcher

BOARD = KanbanBoard(
    board_id="b-gate",
    name="Boot gate",
    settings=BoardSettings(max_concurrent_tasks=3, heartbeat_interval_seconds=1, zombie_timeout_seconds=60),
)


class _Runner:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        self.calls.append(task.task_id)
        return True, "ok"


def _task(task_id: str, status: TaskStatus = TaskStatus.READY) -> KanbanTask:
    return KanbanTask(
        task_id=task_id,
        board_id=BOARD.board_id,
        title=f"Task {task_id}",
        status=status,
        priority=TaskPriority.NORMAL,
    )


async def _store_with_tasks() -> InMemoryKanbanStore:
    store = InMemoryKanbanStore()
    await store.save_board(BOARD)
    for index in range(3):
        await store.save_task(_task(f"t{index}"))
    return store


@pytest.mark.asyncio
async def test_closed_gate_keeps_every_ready_task_queued() -> None:
    store = await _store_with_tasks()
    runner = _Runner()

    async def never() -> bool:
        return False

    dispatchers: dict[str, object] = {}
    await start_dispatcher(store, dispatchers, BOARD.board_id, runner, dispatch_allowed=never)  # type: ignore[arg-type]
    await asyncio.sleep(0.3)
    await shutdown_dispatchers(dispatchers)  # type: ignore[arg-type]

    for index in range(3):
        task = await store.get_task(f"t{index}")
        assert task is not None
        assert task.status == TaskStatus.READY
        assert task.consecutive_failures == 0
    assert runner.calls == []


@pytest.mark.asyncio
async def test_open_gate_runs_the_tasks() -> None:
    store = await _store_with_tasks()
    runner = _Runner()

    async def always() -> bool:
        return True

    dispatchers: dict[str, object] = {}
    await start_dispatcher(store, dispatchers, BOARD.board_id, runner, dispatch_allowed=always)  # type: ignore[arg-type]
    for _ in range(80):
        if len(runner.calls) == 3:
            break
        await asyncio.sleep(0.02)
    await shutdown_dispatchers(dispatchers)  # type: ignore[arg-type]

    assert sorted(runner.calls) == ["t0", "t1", "t2"]


@pytest.mark.asyncio
async def test_dispatcher_started_without_a_gate_is_unchanged() -> None:
    """Runtime callers (a user creates a board) pass no gate, so their behaviour stays as before."""
    store = await _store_with_tasks()
    runner = _Runner()

    dispatchers: dict[str, object] = {}
    await start_dispatcher(store, dispatchers, BOARD.board_id, runner)  # type: ignore[arg-type]
    for _ in range(80):
        if len(runner.calls) == 3:
            break
        await asyncio.sleep(0.02)
    await shutdown_dispatchers(dispatchers)  # type: ignore[arg-type]

    assert sorted(runner.calls) == ["t0", "t1", "t2"]


@pytest.mark.asyncio
async def test_gate_blocks_only_when_no_provider_is_configured() -> None:
    """Only a missing provider blocks dispatch; a broken gate fails open."""
    from types import SimpleNamespace

    configs = SimpleNamespace(providers_dict={"providers": []})

    # The gate imports both helpers at call time, so patching them on their home modules is what it sees.
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config") as resolver,
    ):
        resolver.side_effect = ConfigIncompleteError(
            user_friendly_message={"en": "no provider"},
            technical_details="no provider",
            resolution_steps=[],
            error_code="provider_not_configured",
        )
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is False

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config") as resolver,
    ):
        resolver.side_effect = ValueError("gate itself broke")
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is True
    dispatch_gate.reset_cache()


@pytest.mark.asyncio
async def test_missing_default_model_blocks_only_when_an_unpinned_task_exists() -> None:
    """A task that pins its own model resolves without a default; one that does not, does not."""
    from types import SimpleNamespace

    configs = SimpleNamespace(providers_dict={"providers": [{"id": "openai", "isEnabled": True}]})

    def resolver_raising(*_args: object, **_kwargs: object) -> None:
        raise ConfigIncompleteError(
            user_friendly_message={"en": "no default model"},
            technical_details="no default",
            resolution_steps=[],
            error_code="default_model_not_configured",
        )

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", side_effect=resolver_raising),
        patch.object(dispatch_gate, "_unplanned_task_exists", return_value=False),
    ):
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is True

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", side_effect=resolver_raising),
        patch.object(dispatch_gate, "_unplanned_task_exists", return_value=True),
    ):
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is False
    dispatch_gate.reset_cache()


@pytest.mark.asyncio
async def test_unknown_config_error_code_blocks_dispatch() -> None:
    """An unrecognised ConfigIncompleteError is still a configuration problem: stay conservative."""
    from types import SimpleNamespace

    configs = SimpleNamespace(providers_dict={})
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config") as resolver,
    ):
        resolver.side_effect = ConfigIncompleteError(
            user_friendly_message={"en": "something else"},
            technical_details="other",
            resolution_steps=[],
            error_code="something_else",
        )
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is False
    dispatch_gate.reset_cache()


@pytest.mark.asyncio
async def test_gate_is_memoised_so_hundreds_of_boards_evaluate_once() -> None:
    """Every board asks on every wake cycle; one window must cost one config read, not one per board."""
    from types import SimpleNamespace

    configs = SimpleNamespace(providers_dict={"providers": []})
    dispatch_gate.reset_cache()
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=configs) as loader,
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=None),
    ):
        results = await asyncio.gather(*(dispatch_gate.dispatch_allowed() for _ in range(200)))
    assert all(results) is True
    assert loader.await_count == 1
    dispatch_gate.reset_cache()


@pytest.mark.asyncio
async def test_unreadable_configuration_fails_open_instead_of_holding_forever() -> None:
    """A gate that cannot read at all must not keep the queue silent; the runner reports the error."""
    with patch("app.core.channel_bridge.config_loader.load_user_configs", side_effect=RuntimeError("disk I/O error")):
        dispatch_gate.reset_cache()
        assert await dispatch_gate.dispatch_allowed() is True
    dispatch_gate.reset_cache()


def test_gate_survives_being_called_from_a_second_event_loop() -> None:
    """A process-global gate must not cache an asyncio primitive bound to a finished loop."""

    async def one_call() -> bool:
        return await dispatch_gate.dispatch_allowed()

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=None),
        patch("app.core.channel_bridge.model_resolver.resolve_model_config", return_value=None),
    ):
        dispatch_gate.reset_cache()
        assert asyncio.run(one_call()) is True
        dispatch_gate.reset_cache()
        assert asyncio.run(one_call()) is True
        # And again without a reset: the memo must not be tied to the first loop.
        assert asyncio.run(one_call()) is True
    dispatch_gate.reset_cache()
