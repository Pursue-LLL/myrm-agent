"""Direct-SSE disconnect tolerance: the grace-period checker and the per-turn monitor lifecycle."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

from app.services.agent.stream_session import stream_disconnect
from app.services.agent.stream_session.stream_disconnect import (
    build_disconnect_checker,
    watch_client_disconnect,
)
from app.services.agent.stream_session.stream_session_types import (
    GRACE_PERIOD_SECONDS,
    AgentStreamSession,
)

_FAST_INTERVAL_SECONDS = 0.01


def _session(
    *,
    multiplexed: bool = False,
    disconnected: bool = True,
    has_subscribers: bool = False,
    long_running: bool = False,
    disconnect_time: float | None = None,
) -> AgentStreamSession:
    return cast(
        AgentStreamSession,
        SimpleNamespace(
            request=SimpleNamespace(multiplexed=multiplexed),
            http_request=SimpleNamespace(is_disconnected=AsyncMock(return_value=disconnected)),
            collector=SimpleNamespace(has_subscribers=has_subscribers),
            params=SimpleNamespace(message_id="msg-1"),
            cancel_token=CancellationToken(request_id="msg-1"),
            is_long_running_task=long_running,
            disconnect_time=disconnect_time,
        ),
    )


def _monitor_loops() -> list[asyncio.Task[object]]:
    """Live CancellationMonitor polling tasks: the resource a finished turn must not leave behind."""
    return [task for task in asyncio.all_tasks() if getattr(task.get_coro(), "__qualname__", "").endswith("._monitor_loop")]


async def _until_cancelled(token: CancellationToken) -> None:
    while not token.is_cancelled:
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_connected_client_clears_the_grace_clock() -> None:
    session = _session(disconnected=False, disconnect_time=time.time() - 30)

    assert await build_disconnect_checker(session)() is False
    assert session.disconnect_time is None


@pytest.mark.asyncio
async def test_resubscribed_client_clears_the_grace_clock() -> None:
    session = _session(disconnected=True, has_subscribers=True, disconnect_time=time.time() - 30)

    assert await build_disconnect_checker(session)() is False
    assert session.disconnect_time is None


@pytest.mark.asyncio
async def test_first_detected_disconnect_only_starts_the_grace_clock() -> None:
    session = _session()

    assert await build_disconnect_checker(session)() is False
    assert session.disconnect_time is not None


@pytest.mark.asyncio
async def test_disconnect_within_the_grace_period_keeps_the_turn_running() -> None:
    session = _session(disconnect_time=time.time() - (GRACE_PERIOD_SECONDS - 30))

    assert await build_disconnect_checker(session)() is False


@pytest.mark.asyncio
async def test_disconnect_past_the_grace_period_cancels_the_turn() -> None:
    session = _session(disconnect_time=time.time() - (GRACE_PERIOD_SECONDS + 1))

    assert await build_disconnect_checker(session)() is True


@pytest.mark.asyncio
async def test_long_running_turn_is_never_cancelled_for_a_disconnect() -> None:
    session = _session(long_running=True, disconnect_time=time.time() - (GRACE_PERIOD_SECONDS + 1))

    assert await build_disconnect_checker(session)() is False


class _SpyMonitor:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def start(self) -> None:
        self.events.append("start")

    async def stop(self) -> None:
        self.events.append("stop")


@pytest.fixture
def spy_monitors(monkeypatch: pytest.MonkeyPatch) -> list[_SpyMonitor]:
    created: list[_SpyMonitor] = []

    def factory(**_kwargs: object) -> _SpyMonitor:
        monitor = _SpyMonitor()
        created.append(monitor)
        return monitor

    monkeypatch.setattr(stream_disconnect, "CancellationMonitor", factory)
    return created


@pytest.mark.asyncio
async def test_multiplexed_turn_has_no_connection_to_watch(spy_monitors: list[_SpyMonitor]) -> None:
    async with watch_client_disconnect(_session(multiplexed=True)):
        pass

    assert spy_monitors == []


@pytest.mark.asyncio
async def test_direct_turn_starts_and_stops_exactly_one_monitor(spy_monitors: list[_SpyMonitor]) -> None:
    async with watch_client_disconnect(_session()):
        assert [monitor.events for monitor in spy_monitors] == [["start"]]

    assert [monitor.events for monitor in spy_monitors] == [["start", "stop"]]


@pytest.mark.asyncio
async def test_monitor_is_stopped_when_the_turn_body_raises(spy_monitors: list[_SpyMonitor]) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with watch_client_disconnect(_session()):
            raise RuntimeError("boom")

    assert [monitor.events for monitor in spy_monitors] == [["start", "stop"]]


@pytest.mark.asyncio
async def test_no_polling_task_outlives_a_finished_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_disconnect, "_CHECK_INTERVAL_SECONDS", _FAST_INTERVAL_SECONDS)

    async with watch_client_disconnect(_session(disconnected=False)):
        await asyncio.sleep(5 * _FAST_INTERVAL_SECONDS)
        assert len(_monitor_loops()) == 1

    assert _monitor_loops() == []


@pytest.mark.asyncio
async def test_sustained_disconnect_cancels_the_turn_once_the_grace_period_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stream_disconnect, "_CHECK_INTERVAL_SECONDS", _FAST_INTERVAL_SECONDS)
    monkeypatch.setattr(stream_disconnect, "GRACE_PERIOD_SECONDS", 5 * _FAST_INTERVAL_SECONDS)
    session = _session()

    async with watch_client_disconnect(session):
        await asyncio.wait_for(_until_cancelled(session.cancel_token), timeout=2)

    assert session.cancel_token.cancel_reason == CancelReason.DISCONNECT


@pytest.mark.asyncio
async def test_long_running_turn_survives_a_sustained_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_disconnect, "_CHECK_INTERVAL_SECONDS", _FAST_INTERVAL_SECONDS)
    monkeypatch.setattr(stream_disconnect, "GRACE_PERIOD_SECONDS", 2 * _FAST_INTERVAL_SECONDS)
    session = _session(long_running=True)

    async with watch_client_disconnect(session):
        await asyncio.sleep(15 * _FAST_INTERVAL_SECONDS)

    assert session.cancel_token.is_cancelled is False
