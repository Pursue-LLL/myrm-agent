"""The lifespan recovers state after the socket is bound and starts the warm-up once the first screen has loaded.

[INPUT]
- app.server.lifespan.background (POS: schedules the boot's background tasks)

[OUTPUT]
- Coverage that recovery starts after the bind delay, that the warm-up waits for the first screen (readiness reporting the
  database ready) or the fallback delay, that polling readiness cannot push the warm-up back, that every task runs, that a
  failure is logged, that the settle step waits for the warm-up, and that a shutdown cancels the starts that have not fired

[POS]
Server tests. Uvicorn binds its socket only after the lifespan yields, and the first screen's requests follow the readiness
response; warm-up work that starts earlier competes with them for the single event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator

import pytest

from app.server.lifespan import background, startup
from app.server.lifespan.state import logger

_RECOVERY_TASKS = ("orphaned-goals",)
_WARMUP_TASKS = ("warmup", "kanban-dispatchers", "startup-event", "trunk-templates", "tool-layers")
_ALL_TASKS = sorted((*_RECOVERY_TASKS, *_WARMUP_TASKS))


@pytest.fixture(autouse=True)
def _no_pending_starts() -> Iterator[None]:
    background.cancel_scheduled_background_work()
    background._running.clear()
    yield
    background.cancel_scheduled_background_work()


def _install_fakes(monkeypatch: pytest.MonkeyPatch, started: list[str], *, failing: str | None = None) -> asyncio.Event:
    """Replace the six background coroutines; each records its start, waits for ``release``, then ends or fails.

    The fallback is far away, so only readiness (or a test that shortens it) can start the warm-up.
    """
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
    monkeypatch.setattr(startup, "_dispatch_startup_event", fake("startup-event"))
    monkeypatch.setattr(startup, "_seed_trunk_templates", fake("trunk-templates"))
    monkeypatch.setattr(startup, "_preload_agent_tool_layers", fake("tool-layers"))
    monkeypatch.setattr(background, "RECOVERY_DELAY_SECONDS", 0.02)
    monkeypatch.setattr(background, "FIRST_SCREEN_SETTLE_SECONDS", 0.2)
    monkeypatch.setattr(background, "WARMUP_FALLBACK_DELAY_SECONDS", 30.0)
    return release


def _capture_settle(monkeypatch: pytest.MonkeyPatch) -> list[asyncio.Future[object]]:
    settled: list[asyncio.Future[object]] = []
    monkeypatch.setattr(background, "settle_collection_after", settled.append)
    return settled


async def _until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    give_up_at = loop.time() + timeout
    while not condition():
        assert loop.time() < give_up_at, "the background work did not reach the expected state in time"
        await asyncio.sleep(0.01)


async def _boot_and_load_first_screen(started: list[str]) -> None:
    """Schedule the background work and report readiness; returns once recovery and the warm-up have both started."""
    background.schedule_background_work()
    background.start_warmup_after_first_screen()
    await _until(lambda: sorted(started) == _ALL_TASKS)


async def test_recovery_starts_after_the_bind_delay_and_the_warmup_waits_for_the_first_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []
    _install_fakes(monkeypatch, started)
    _capture_settle(monkeypatch)

    background.schedule_background_work()
    assert started == []

    await _until(lambda: started == list(_RECOVERY_TASKS))
    await asyncio.sleep(0.3)
    assert started == list(_RECOVERY_TASKS)


async def test_readiness_starts_the_warmup_after_the_settle_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)
    loop = asyncio.get_running_loop()

    background.schedule_background_work()
    await _until(lambda: started == list(_RECOVERY_TASKS))
    asked_at = loop.time()
    background.start_warmup_after_first_screen()
    await asyncio.sleep(0)
    assert started == list(_RECOVERY_TASKS)

    await _until(lambda: sorted(started) == _ALL_TASKS)
    assert loop.time() - asked_at >= background.FIRST_SCREEN_SETTLE_SECONDS - 0.01

    release.set()
    await settled[0]


async def test_polling_readiness_does_not_push_the_warmup_back(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)
    loop = asyncio.get_running_loop()

    background.schedule_background_work()
    give_up_at = loop.time() + 5.0
    while "warmup" not in started and loop.time() < give_up_at:
        background.start_warmup_after_first_screen()
        await asyncio.sleep(0.02)

    assert "warmup" in started

    release.set()
    await settled[0]


async def test_the_fallback_starts_the_warmup_when_no_client_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)
    monkeypatch.setattr(background, "WARMUP_FALLBACK_DELAY_SECONDS", 0.1)

    background.schedule_background_work()
    await _until(lambda: sorted(started) == _ALL_TASKS)

    release.set()
    await settled[0]


async def test_readiness_after_the_warmup_started_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    await _boot_and_load_first_screen(started)
    background.start_warmup_after_first_screen()
    await asyncio.sleep(0.3)

    assert sorted(started) == _ALL_TASKS
    assert len(settled) == 1

    release.set()
    await settled[0]


async def test_readiness_without_a_scheduled_start_starts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    background.start_warmup_after_first_screen()
    await asyncio.sleep(0.3)

    assert started == []
    assert settled == []


async def test_the_settle_step_waits_for_every_task_and_the_loop_holds_them_until_then(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    await _boot_and_load_first_screen(started)
    [boot_work] = settled
    assert not boot_work.done()
    assert len(background._running) == len(_ALL_TASKS)

    release.set()
    await boot_work

    assert background._running == set()


async def test_a_failed_task_is_logged_and_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started, failing="warmup")
    settled = _capture_settle(monkeypatch)

    with caplog.at_level("ERROR", logger=logger.name):
        await _boot_and_load_first_screen(started)
        release.set()
        await settled[0]

    assert sorted(started) == _ALL_TASKS
    assert "Background task" in caplog.text
    assert "warmup exploded" in caplog.text


async def test_a_shutdown_cancels_both_starts_and_a_later_readiness_starts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    background.schedule_background_work()
    background.cancel_scheduled_background_work()
    background.start_warmup_after_first_screen()
    await asyncio.sleep(0.3)

    assert started == []
    assert settled == []
    assert background._running == set()


async def test_a_shutdown_after_recovery_started_still_keeps_the_warmup_from_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    background.schedule_background_work()
    await _until(lambda: started == list(_RECOVERY_TASKS))

    background.cancel_scheduled_background_work()
    background.start_warmup_after_first_screen()
    await asyncio.sleep(0.3)

    assert started == list(_RECOVERY_TASKS)
    assert settled == []

    release.set()
    await _until(lambda: background._running == set())


async def test_cancelling_after_the_start_leaves_the_running_tasks_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    release = _install_fakes(monkeypatch, started)
    settled = _capture_settle(monkeypatch)

    await _boot_and_load_first_screen(started)
    background.cancel_scheduled_background_work()

    assert len(background._running) == len(_ALL_TASKS)
    release.set()
    await settled[0]
    assert background._running == set()
