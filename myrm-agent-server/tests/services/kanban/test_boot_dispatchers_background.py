"""A server boot starts the kanban dispatchers in the background, so its length does not grow with the board count.

A machine with 525 boards spent seconds in this step: every board read its own row again, and each dispatcher ran
its first queries before the next board was started. The boot now reads the boards once, starts them in batches
off the readiness path, and shutdown cancels a start that is still going.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.lifecycle.schedulers.kanban import start_kanban_dispatchers
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


@pytest.mark.asyncio
async def test_boot_start_returns_before_any_dispatcher_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(3))

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
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

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
    await _boot_started(service)

    assert len(service._dispatchers) == 4
    assert reads == []
    await service.shutdown()


@pytest.mark.asyncio
async def test_boot_start_pauses_between_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(5))
    pauses: list[float] = []

    async def record_pause(delay: float) -> None:
        pauses.append(delay)

    monkeypatch.setattr(mixin, "_BOOT_BATCH_SIZE", 2)
    monkeypatch.setattr(mixin, "asyncio", SimpleNamespace(sleep=record_pause, CancelledError=asyncio.CancelledError))

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
    await _boot_started(service)

    assert pauses == [mixin._BOOT_BATCH_PAUSE_SECONDS] * 2  # after the 2nd and the 4th board
    assert len(service._dispatchers) == 5
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

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
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

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
    await _boot_started(service)

    assert [call["dispatch_allowed"] for call in calls] == [None]


@pytest.mark.asyncio
async def test_boot_start_with_no_boards_never_consults_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, [])

    async def forbidden() -> bool:
        raise AssertionError("the gate costs a config read and has nothing to gate without boards")

    monkeypatch.setattr(dispatch_gate, "dispatch_allowed", forbidden)

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
    await _boot_started(service)

    assert service._dispatchers == {}


@pytest.mark.asyncio
async def test_shutdown_cancels_a_boot_start_that_is_still_going(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, _boards(3))
    entered = asyncio.Event()

    async def blocked(*args: object, **kwargs: object) -> object:
        entered.set()
        await asyncio.Event().wait()
        return None

    monkeypatch.setattr(mixin, "run_start_dispatcher", blocked)

    service.start_boot_dispatchers(_RUNNER)  # type: ignore[arg-type]
    await entered.wait()
    await asyncio.wait_for(service.shutdown(), timeout=2)

    task = service._boot_dispatchers_task
    assert task is not None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_the_lifecycle_starter_does_not_wait_for_the_dispatchers(monkeypatch: pytest.MonkeyPatch) -> None:
    service = KanbanService()
    started: list[object] = []
    monkeypatch.setattr(KanbanService, "get_instance", classmethod(lambda cls: service))
    monkeypatch.setattr(service, "recover_stale_tasks", AsyncMock(return_value=0))
    monkeypatch.setattr(service, "start_boot_dispatchers", started.append)

    await start_kanban_dispatchers()

    assert len(started) == 1
    assert service._runner is started[0]
