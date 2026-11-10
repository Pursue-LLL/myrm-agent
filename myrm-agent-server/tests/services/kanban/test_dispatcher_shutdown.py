"""A shutdown ends the kanban boot start and the dispatchers without cancelling a task inside a database call.

Cancelling a task that is in the middle of a pooled database call can make the driver tear the connection down twice
and leave the shutdown waiting on a worker thread that has already exited, so a server asked to quit while the
dispatchers were starting never finished quitting. The boot start therefore leaves at a step boundary, cancellation is
only a bounded fallback, and the dispatchers are stopped at the same time, so waits do not add up with the board count.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.stores import InMemoryKanbanStore
from myrm_agent_harness.toolkits.kanban.types import BoardSettings, KanbanBoard

from app.services.kanban import KanbanService, dispatch_gate
from app.services.kanban.dispatcher_lifecycle import shutdown_dispatchers, stop_dispatcher
from app.services.kanban.service_mixins import query_dispatcher_mixin as mixin

# The boards hold no tasks, so the runner is never invoked.
_RUNNER = SimpleNamespace()


def _boards(count: int) -> list[KanbanBoard]:
    return [
        KanbanBoard(board_id=f"b{index}", name=f"Board {index}", settings=BoardSettings(heartbeat_interval_seconds=1))
        for index in range(count)
    ]


async def _service(monkeypatch: pytest.MonkeyPatch, count: int) -> KanbanService:
    boards = _boards(count)
    store = InMemoryKanbanStore()
    for board in boards:
        await store.save_board(board)
    service = KanbanService()
    monkeypatch.setattr(service, "_store", store)
    service.set_runner(_RUNNER)  # type: ignore[arg-type]

    async def list_boards(*, project_id: str | None = None) -> list[KanbanBoard]:
        return list(boards)

    async def gate() -> bool:
        return True

    monkeypatch.setattr(service, "list_boards", list_boards)
    monkeypatch.setattr(dispatch_gate, "dispatch_allowed", gate)
    return service


def _fake_dispatcher() -> KanbanDispatcher:
    return SimpleNamespace(stop=AsyncMock())  # type: ignore[return-value]


@pytest.mark.asyncio
async def test_shutdown_ends_a_boot_start_that_is_still_waiting_without_cancelling_it(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, 3)

    service.start_boot_dispatchers(start_after_seconds=3600)
    await asyncio.sleep(0)
    await asyncio.wait_for(service.shutdown(), timeout=2)

    task = service._boot_dispatchers_task
    assert task is not None
    assert task.done()
    assert not task.cancelled()
    assert service._dispatchers == {}


@pytest.mark.asyncio
async def test_shutdown_lets_the_dispatcher_being_started_finish_and_starts_no_other(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, 3)
    entered = asyncio.Event()
    release = asyncio.Event()
    started: list[str] = []

    async def slow_start(
        store: object, dispatchers: dict[str, KanbanDispatcher], board_id: str, *args: object, **kwargs: object
    ) -> object:
        entered.set()
        await release.wait()
        started.append(board_id)
        dispatchers[board_id] = _fake_dispatcher()
        return dispatchers[board_id]

    monkeypatch.setattr(mixin, "run_start_dispatcher", slow_start)

    service.start_boot_dispatchers()
    await entered.wait()
    stopping = asyncio.create_task(service.shutdown())
    await asyncio.sleep(0.05)
    assert not stopping.done()  # the step in flight is waited for, not cancelled

    release.set()
    await asyncio.wait_for(stopping, timeout=2)

    task = service._boot_dispatchers_task
    assert task is not None
    assert task.done()
    assert not task.cancelled()
    assert started == ["b0"]
    assert service._dispatchers == {}


@pytest.mark.asyncio
async def test_shutdown_cancels_a_boot_start_that_does_not_leave_in_time(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, 3)
    entered = asyncio.Event()
    monkeypatch.setattr(mixin, "_BOOT_START_GRACE_SECONDS", 0.05)

    async def blocked(*args: object, **kwargs: object) -> object:
        entered.set()
        await asyncio.Event().wait()
        return None

    monkeypatch.setattr(mixin, "run_start_dispatcher", blocked)

    service.start_boot_dispatchers()
    await entered.wait()
    await asyncio.wait_for(service.shutdown(), timeout=2)

    task = service._boot_dispatchers_task
    assert task is not None
    assert task.cancelled()


@pytest.mark.asyncio
async def test_shutdown_goes_on_without_a_boot_start_that_ignores_cancellation(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    service = await _service(monkeypatch, 3)
    entered = asyncio.Event()
    release = asyncio.Event()
    monkeypatch.setattr(mixin, "_BOOT_START_GRACE_SECONDS", 0.05)

    async def deaf(*args: object, **kwargs: object) -> object:
        entered.set()
        while not release.is_set():
            try:
                await asyncio.wait_for(release.wait(), timeout=3600)
            except asyncio.CancelledError:
                continue
        return None

    monkeypatch.setattr(mixin, "run_start_dispatcher", deaf)

    service.start_boot_dispatchers()
    await entered.wait()
    with caplog.at_level("WARNING", logger=mixin.logger.name):
        await asyncio.wait_for(service.shutdown(), timeout=2)

    assert "did not end after cancellation" in caplog.text
    task = service._boot_dispatchers_task
    assert task is not None
    assert not task.done()

    release.set()
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_a_boot_start_after_a_shutdown_is_not_stopped_by_it(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, 2)
    await service.shutdown()

    service.start_boot_dispatchers()
    task = service._boot_dispatchers_task
    assert task is not None
    await task

    assert sorted(service._dispatchers) == ["b0", "b1"]
    await service.shutdown()


@pytest.mark.asyncio
async def test_shutdown_stops_real_dispatchers_that_the_boot_started(monkeypatch: pytest.MonkeyPatch) -> None:
    service = await _service(monkeypatch, 4)

    service.start_boot_dispatchers()
    task = service._boot_dispatchers_task
    assert task is not None
    await task
    dispatchers = list(service._dispatchers.values())
    assert len(dispatchers) == 4
    assert all(dispatcher._running for dispatcher in dispatchers)

    await asyncio.wait_for(service.shutdown(), timeout=5)

    assert service._dispatchers == {}
    assert not any(dispatcher._running for dispatcher in dispatchers)


@pytest.mark.asyncio
async def test_dispatchers_are_stopped_at_the_same_time() -> None:
    arrived = 0
    all_arrived = asyncio.Event()

    async def stop() -> None:
        nonlocal arrived
        arrived += 1
        if arrived == 3:
            all_arrived.set()
        # Stopped one after the other, the first stop would wait here for two that never begin.
        await asyncio.wait_for(all_arrived.wait(), timeout=1)

    dispatchers = {board_id: SimpleNamespace(stop=stop) for board_id in ("b0", "b1", "b2")}

    await shutdown_dispatchers(dispatchers)  # type: ignore[arg-type]

    assert dispatchers == {}


@pytest.mark.asyncio
async def test_a_dispatcher_that_fails_to_stop_does_not_keep_the_others_running(caplog: pytest.LogCaptureFixture) -> None:
    healthy = SimpleNamespace(stop=AsyncMock())
    broken = SimpleNamespace(stop=AsyncMock(side_effect=RuntimeError("stop exploded")))
    dispatchers = {"ok": healthy, "broken": broken}

    with caplog.at_level("ERROR"):
        await shutdown_dispatchers(dispatchers)  # type: ignore[arg-type]

    healthy.stop.assert_awaited_once()
    assert list(dispatchers) == ["broken"]
    assert "board broken failed to stop" in caplog.text
    assert "stop exploded" in caplog.text


@pytest.mark.asyncio
async def test_a_board_started_again_while_it_stops_keeps_its_new_dispatcher() -> None:
    replacement = SimpleNamespace(stop=AsyncMock())
    dispatchers: dict[str, KanbanDispatcher] = {}

    async def stop() -> None:
        dispatchers["b0"] = replacement  # type: ignore[assignment]

    dispatchers["b0"] = SimpleNamespace(stop=stop)  # type: ignore[assignment]

    assert await stop_dispatcher(dispatchers, "b0") is True

    assert dispatchers["b0"] is replacement
    assert await stop_dispatcher(dispatchers, "unknown") is False
