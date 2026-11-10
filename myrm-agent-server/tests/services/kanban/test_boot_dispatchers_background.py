"""A server boot starts the kanban dispatchers in the background, so its length does not grow with the board count.

A machine with 525 boards spent seconds in this step: every board read its own row again, and each dispatcher ran
its first queries before the next board was started. The boot now prepares kanban cheaply before the HTTP bind,
and starts the dispatchers afterwards: the boards are read once, started in batches, and a first start can be held
back. How a shutdown ends a start that is waiting or going is covered in test_dispatcher_shutdown.py.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.lifecycle.schedulers import kanban as lifecycle
from app.services.kanban import KanbanService, dispatch_gate
from app.services.kanban.service_mixins import query_dispatcher_mixin as mixin

# The boards hold no tasks, so the runner is never invoked.
_RUNNER = SimpleNamespace()


def _boards(count: int) -> list[KanbanBoard]:
    return [
        KanbanBoard(board_id=f"b{index}", name=f"Board {index}", settings=BoardSettings(heartbeat_interval_seconds=1))
        for index in range(count)
    ]


async def _service(monkeypatch: pytest.MonkeyPatch, boards: list[KanbanBoard], *, gate_open: bool = True) -> KanbanService:
    store = InMemoryKanbanStore()
    for board in boards:
        await store.save_board(board)
    service = KanbanService()
    monkeypatch.setattr(service, "_store", store)
    service.set_runner(_RUNNER)  # type: ignore[arg-type]

    async def list_boards(*, project_id: str | None = None) -> list[KanbanBoard]:
        return list(boards)

    async def gate() -> bool:
        return gate_open

    monkeypatch.setattr(service, "list_boards", list_boards)
    monkeypatch.setattr(dispatch_gate, "dispatch_allowed", gate)
    return service


async def _boot_started(service: KanbanService) -> None:
    task = service._boot_dispatchers_task
    assert task is not None
    await task


def _record_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the mixin's interruptible sleep with a recorder so pauses and the start delay are observable."""
    sleeps: list[float] = []

    async def record(stop: asyncio.Event, delay: float) -> bool:
        sleeps.append(delay)
        return stop.is_set()

    monkeypatch.setattr(mixin, "_sleep_unless_stopped", record)
    return sleeps


@pytest.mark.asyncio
async def test_boot_start_returns_before_any_dispatcher_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(3))

    service.start_boot_dispatchers()
    assert service._dispatchers == {}

    await _boot_started(service)
    assert sorted(service._dispatchers) == ["b0", "b1", "b2"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_does_not_read_the_listed_boards_again(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(4))
    reads: list[str] = []
    original = service.store.get_board

    async def counting_get_board(board_id: str) -> KanbanBoard | None:
        reads.append(board_id)
        return await original(board_id)

    monkeypatch.setattr(service.store, "get_board", counting_get_board)

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert len(service._dispatchers) == 4
    assert reads == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_pauses_between_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(5))
    sleeps = _record_sleeps(monkeypatch)
    monkeypatch.setattr(mixin, "_BOOT_BATCH_SIZE", 2)

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert sleeps == [mixin._BOOT_BATCH_PAUSE_SECONDS] * 2  # after the 2nd and the 4th board
    assert len(service._dispatchers) == 5
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_holds_back_the_first_start_by_the_requested_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(1))
    sleeps = _record_sleeps(monkeypatch)
    listed: list[int] = []
    original = service.list_boards

    async def list_after_sleep(*, project_id: str | None = None) -> list[KanbanBoard]:
        listed.append(len(sleeps))
        return await original(project_id=project_id)

    monkeypatch.setattr(service, "list_boards", list_after_sleep)

    service.start_boot_dispatchers(start_after_seconds=0.75)
    await _boot_started(service)

    assert sleeps == [0.75]
    assert listed == [1]  # the boards are read only once the delay has passed
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_does_not_replace_a_dispatcher_that_is_already_running(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(3))
    live = SimpleNamespace(stop=AsyncMock())
    service._dispatchers["b1"] = live  # type: ignore[assignment]

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert service._dispatchers["b1"] is live
    live.stop.assert_not_awaited()
    assert sorted(service._dispatchers) == ["b0", "b1", "b2"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_hands_each_dispatcher_its_board_and_the_closed_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    boards = _boards(2)
    service = await _service(monkeypatch, boards, gate_open=False)
    calls: list[dict[str, object]] = []

    async def fake_start(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(mixin, "run_start_dispatcher", fake_start)

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert [call["board"] for call in calls] == boards
    assert all(call["rescue_orphans"] is False for call in calls)
    assert all(call["dispatch_allowed"] is dispatch_gate.dispatch_allowed for call in calls)


@pytest.mark.asyncio
async def test_boot_start_passes_no_gate_when_a_model_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(1), gate_open=True)
    calls: list[dict[str, object]] = []

    async def fake_start(*args: object, **kwargs: object) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(mixin, "run_start_dispatcher", fake_start)

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert [call["dispatch_allowed"] for call in calls] == [None]


@pytest.mark.asyncio
async def test_boot_start_with_no_boards_never_consults_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, [])

    async def forbidden() -> bool:
        raise AssertionError("the gate costs a config read and has nothing to gate without boards")

    monkeypatch.setattr(dispatch_gate, "dispatch_allowed", forbidden)

    service.start_boot_dispatchers()
    await _boot_started(service)

    assert service._dispatchers == {}


@pytest.mark.asyncio
async def test_boot_start_needs_the_runner_prepared_first() -> None:
    service = KanbanService()

    with pytest.raises(RuntimeError, match="runner"):
        service.start_boot_dispatchers()


@pytest.mark.asyncio
async def test_preparation_recovers_stale_tasks_and_wires_the_runner_without_starting_dispatchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = KanbanService()
    monkeypatch.setattr(KanbanService, "get_instance", classmethod(lambda cls: service))
    recover = AsyncMock(return_value=0)
    monkeypatch.setattr(service, "recover_stale_tasks", recover)
    monkeypatch.setattr(service, "start_boot_dispatchers", MagicMock(side_effect=AssertionError("not before the bind")))

    await lifecycle.prepare_kanban_dispatch()

    recover.assert_awaited_once()
    assert service._runner is not None
    assert service._boot_dispatchers_task is None


@pytest.mark.asyncio
async def test_the_lifecycle_starter_hands_over_the_boot_delay_and_does_not_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    service = KanbanService()
    monkeypatch.setattr(KanbanService, "get_instance", classmethod(lambda cls: service))
    starter = MagicMock()
    monkeypatch.setattr(service, "start_boot_dispatchers", starter)

    await lifecycle.start_kanban_dispatchers()

    starter.assert_called_once_with(start_after_seconds=lifecycle.BOOT_DISPATCH_DELAY_SECONDS)
