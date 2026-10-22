"""WakeScheduleReporter: push the next must-wake time to the control plane when it changes or ages."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.sandbox_wake.reporter import WakeScheduleEndpoint, WakeScheduleReporter

_ENDPOINT = WakeScheduleEndpoint(
    url="http://cp/api/internal/sandboxes/sb-1/wake-schedule",
    headers={"X-Telemetry-Token": "tok", "X-Sandbox-Id": "sb-1"},
)
_NEXT = "app.services.sandbox_wake.reporter.earliest_scheduled_wake"


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _reporter(*, clock: float = 1000.0) -> WakeScheduleReporter:
    return WakeScheduleReporter(_ENDPOINT, clock=lambda: clock)


async def _run_loop_sleeps(reporter: WakeScheduleReporter, clock: _Clock, *, ticks: int) -> list[float]:
    """Run the report loop for ``ticks`` iterations; sleeping advances the clock. Returns the sleep lengths."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        clock.now += delay
        if len(sleeps) == ticks:
            raise asyncio.CancelledError

    with patch("app.services.sandbox_wake.reporter.asyncio.sleep", fake_sleep), pytest.raises(asyncio.CancelledError):
        await reporter._run()
    return sleeps


def _push_mock(reporter: WakeScheduleReporter, *, ok: bool = True) -> AsyncMock:
    mock = AsyncMock(return_value=ok)
    reporter._push = mock  # type: ignore[method-assign]
    return mock


@pytest.mark.asyncio
async def test_first_report_is_always_pushed_even_when_nothing_is_scheduled() -> None:
    reporter = _reporter()
    push = _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=None)):
        assert await reporter.report_once() is True

    push.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_unchanged_value_is_not_pushed_again() -> None:
    reporter = _reporter()
    push = _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=2000.0)):
        await reporter.report_once()
        await reporter.report_once()

    push.assert_awaited_once_with(2000.0)


@pytest.mark.asyncio
async def test_unchanged_value_is_repeated_as_a_heartbeat() -> None:
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, heartbeat=600.0, clock=clock)
    push = _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=9000.0)):
        for now in (1000.0, 1599.0, 1600.0, 1601.0):
            clock.now = now
            await reporter.report_once()

    assert [call.args[0] for call in push.await_args_list] == [9000.0, 9000.0]


@pytest.mark.asyncio
async def test_failed_heartbeat_is_retried_on_the_next_report() -> None:
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, heartbeat=600.0, clock=clock)
    push = _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=9000.0)):
        await reporter.report_once()
        clock.now = 1600.0
        push.return_value = False
        assert await reporter.report_once() is False
        push.return_value = True
        assert await reporter.report_once() is True
        assert await reporter.report_once() is True

    assert push.await_count == 3


@pytest.mark.asyncio
async def test_changed_value_is_pushed_including_clear() -> None:
    reporter = _reporter()
    push = _push_mock(reporter)

    for value in (2000.0, 1500.0, None):
        with patch(_NEXT, AsyncMock(return_value=value)):
            await reporter.report_once()

    assert [call.args[0] for call in push.await_args_list] == [2000.0, 1500.0, None]


@pytest.mark.asyncio
async def test_failed_push_is_retried_on_the_next_report() -> None:
    reporter = _reporter()
    push = _push_mock(reporter, ok=False)

    with patch(_NEXT, AsyncMock(return_value=2000.0)):
        assert await reporter.report_once() is False
        push.return_value = True
        assert await reporter.report_once() is True
        assert await reporter.report_once() is True

    assert push.await_count == 2


@pytest.mark.asyncio
async def test_loop_checks_again_when_the_reported_time_arrives() -> None:
    """Past the lead time the earliest schedule moves on; the control plane must hear it within seconds."""
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, clock=clock)
    _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=1010.0)):
        assert await _run_loop_sleeps(reporter, clock, ticks=1) == [10.0]


@pytest.mark.asyncio
async def test_loop_keeps_its_cadence_when_the_reported_time_is_far_or_nothing_is_scheduled() -> None:
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, clock=clock)
    _push_mock(reporter)

    for value in (9000.0, None):
        with patch(_NEXT, AsyncMock(return_value=value)):
            assert await _run_loop_sleeps(reporter, clock, ticks=1) == [30.0]


@pytest.mark.asyncio
async def test_loop_never_waits_less_than_the_recheck_floor() -> None:
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, clock=clock)
    _push_mock(reporter)

    with patch(_NEXT, AsyncMock(return_value=1000.5)):
        assert await _run_loop_sleeps(reporter, clock, ticks=1) == [2.0]


@pytest.mark.asyncio
async def test_loop_does_not_spin_on_a_stale_reported_time_while_pushes_fail() -> None:
    clock = _Clock(1000.0)
    reporter = WakeScheduleReporter(_ENDPOINT, clock=clock)
    push = _push_mock(reporter)
    push.side_effect = [True, False]

    with patch(_NEXT, AsyncMock(side_effect=[1005.0, 2000.0])):
        assert await _run_loop_sleeps(reporter, clock, ticks=2) == [5.0, 30.0]


@pytest.mark.asyncio
async def test_push_sends_time_with_sandbox_scoped_headers() -> None:
    reporter = _reporter()
    client = AsyncMock()
    client.put.return_value = httpx.Response(200, request=httpx.Request("PUT", _ENDPOINT.url))
    client.__aenter__.return_value = client

    with patch("app.services.sandbox_wake.reporter.httpx.AsyncClient", return_value=client):
        assert await reporter._push(2000.0) is True

    client.put.assert_awaited_once_with(_ENDPOINT.url, json={"next_wake_at": 2000.0}, headers=_ENDPOINT.headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 429, 500])
async def test_push_failure_statuses_report_false(status: int) -> None:
    reporter = _reporter()
    client = AsyncMock()
    client.put.return_value = httpx.Response(status, request=httpx.Request("PUT", _ENDPOINT.url))
    client.__aenter__.return_value = client

    with patch("app.services.sandbox_wake.reporter.httpx.AsyncClient", return_value=client):
        assert await reporter._push(2000.0) is False


@pytest.mark.asyncio
async def test_unreachable_control_plane_reports_false() -> None:
    reporter = _reporter()
    client = AsyncMock()
    client.put.side_effect = httpx.ConnectError("refused")
    client.__aenter__.return_value = client

    with patch("app.services.sandbox_wake.reporter.httpx.AsyncClient", return_value=client):
        assert await reporter._push(2000.0) is False


@pytest.mark.asyncio
async def test_without_control_plane_the_reporter_never_starts() -> None:
    reporter = WakeScheduleReporter(None)

    await reporter.start()

    assert reporter._task is None


def test_endpoint_requires_url_token_and_sandbox_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    from app.config.settings import settings

    cp = settings.control_plane
    monkeypatch.setattr(cp, "url", "http://cp:8001/")
    monkeypatch.setattr(cp, "telemetry_token", SecretStr("tok"))
    monkeypatch.setattr(cp, "sandbox_id", "sb-1")

    endpoint = WakeScheduleEndpoint.from_settings()
    assert endpoint is not None
    assert endpoint.url == "http://cp:8001/api/internal/sandboxes/sb-1/wake-schedule"
    assert endpoint.headers == {"X-Telemetry-Token": "tok", "X-Sandbox-Id": "sb-1"}

    for field, empty in (("url", ""), ("telemetry_token", SecretStr("")), ("sandbox_id", " ")):
        with monkeypatch.context() as patched:
            patched.setattr(cp, field, empty)
            assert WakeScheduleEndpoint.from_settings() is None
