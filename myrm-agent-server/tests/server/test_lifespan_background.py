"""The lifespan starts warmup and housekeeping after the socket is bound, and ends the boot GC pause with them.

[INPUT]
- app.server.lifespan.background (POS: schedules the boot's background tasks)

[OUTPUT]
- Coverage that nothing starts before the delay, that every task runs, that a failure is logged, that the
  settle step waits for all of them, and that a shutdown within the delay cancels the start

[POS]
Server tests. Uvicorn binds its socket only after the lifespan yields; background work that starts earlier delays
the bind by the length of its first synchronous slices on the single event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from app.server.lifespan import background

_TASK_NAMES = ("warmup", "orphaned-goals", "kanban-dispatchers", "startup-event", "trunk-templates", "tool-layers")


def _install_fakes(monkeypatch: pytest.MonkeyPatch, started: list[str], *, failing: str | None = None) -> asyncio.Event:
    """Replace the six background coroutines; each records its start, waits for ``release``, then ends or fails."""
    release = asyncio.Event()

    def fake(name: str) -> Callable[[], Awaitable[None]]:
        async def run() -> None:
            started.append(name)
            await release.wait()
            if name == failing:
                raise RuntimeError(f"{name} exploded")

        return run

    monkeypatch.setattr(background, "run_async_warmup", fake("warmup"))
    monkeypatch.setattr(background, "pause_orphaned_active_goals", fake("orphaned-goals"))
    monkeypatch.setattr(background, "start_kanban_dispatchers", fake("kanban-dispatchers"))
    monkeypatch.setattr(background.startup, "_dispatch_startup_event", fake("startup-event"))
    monkeypatch.setattr(background.startup, "_seed_trunk_templates", fake("trunk-templates"))
    monkeypatch.setattr(background.startup, "_preload_agent_tool_layers", fake("tool-layers"))
    monkeypatch.setattr(background, "BACKGROUND_START_DELAY_SECONDS", 0.05)
    return release


async def test_nothing_starts_before_the_delay_and_every_task_starts_after_it(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)

    background.schedule_background_work()
    await asyncio.sleep(0.01)
    assert started == []

    await asyncio.sleep(0.2)
    assert sorted(started) == sorted(_TASK_NAMES)

    release.set()
    await settled[0]


async def test_the_settle_step_waits_for_every_task_and_the_loop_holds_them_until_then(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)

    background.schedule_background_work()
    await asyncio.sleep(0.2)
    [boot_work] = settled
    assert not boot_work.done()
    assert len(background._running) == len(_TASK_NAMES)

    release.set()
    await boot_work

    assert background._running == set()


async def test_a_failed_task_is_logged_and_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started, failing="warmup")
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)

    with caplog.at_level("ERROR", logger=background.logger.name):
        background.schedule_background_work()
        await asyncio.sleep(0.2)
        release.set()
        await settled[0]

    assert sorted(started) == sorted(_TASK_NAMES)
    assert "Background task" in caplog.text
    assert "warmup exploded" in caplog.text


async def test_a_shutdown_within_the_delay_cancels_the_start(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    _install_fakes(monkeypatch, started)
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)

    background.schedule_background_work()
    background.cancel_scheduled_background_work()
    await asyncio.sleep(0.2)

    assert started == []
    assert settled == []
    assert background._running == set()


async def test_cancelling_after_the_start_leaves_the_running_tasks_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)

    background.schedule_background_work()
    await asyncio.sleep(0.2)
    background.cancel_scheduled_background_work()

    assert len(background._running) == len(_TASK_NAMES)
    release.set()
    await settled[0]
    assert background._running == set()
