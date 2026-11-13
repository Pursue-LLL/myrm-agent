"""Unit tests for bounded page health primitives (abort stalled navigation, liveness probe)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import BrowserSessionError
from myrm_agent_harness.toolkits.browser.utils import page_health
from myrm_agent_harness.toolkits.browser.utils.page_health import (
    DriverClosedError,
    PageUnresponsiveError,
    abort_pending_navigation,
    is_driver_closed_error,
    probe_alive,
    probe_browser_alive,
)
from tests.toolkits.browser._fake_pages import FakeCdp, FakePage

_FAST_S = 0.05
_HANG_BOUND_S = 1.0  # generous wall-clock ceiling for "returned within the (patched) bound"
_DRIVER_GONE = "Browser.new_browser_cdp_session: Connection closed while reading from the driver"


@pytest.fixture(autouse=True)
def _short_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page_health, "_ABORT_TIMEOUT_S", _FAST_S)
    monkeypatch.setattr(page_health, "_DETACH_TIMEOUT_S", _FAST_S)
    monkeypatch.setattr(page_health, "_PROBE_TIMEOUT_S", _FAST_S)


async def _elapsed(coro) -> float:
    started = time.monotonic()
    await coro
    return time.monotonic() - started


def test_page_unresponsive_error_is_a_session_error() -> None:
    assert issubclass(PageUnresponsiveError, BrowserSessionError)


def test_driver_closed_error_is_a_session_error() -> None:
    assert issubclass(DriverClosedError, BrowserSessionError)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("BrowserType.launch: Connection closed while reading from the driver", True),
        ("Page.goto: Connection closed while reading from the driver", True),
        ("browsertype.launch: CONNECTION CLOSED WHILE READING FROM THE DRIVER", True),
        ("Browser closed unexpectedly", False),
        ("Target page, context or browser has been closed", False),
        ("net::ERR_CONNECTION_CLOSED at https://example.com/", False),
        ("", False),
    ],
)
def test_only_an_exited_driver_reads_as_one(message: str, expected: bool) -> None:
    assert is_driver_closed_error(Exception(message)) is expected


class TestAbortPendingNavigation:
    async def test_stops_loading_over_cdp_and_detaches(self) -> None:
        cdp = FakeCdp()
        page = FakePage(cdp=cdp)

        await abort_pending_navigation(page)  # type: ignore[arg-type]

        assert cdp.sent == ["Page.stopLoading"]
        assert cdp.detach_called
        assert page.evaluated == []  # a healthy CDP path never touches the page itself

    async def test_falls_back_to_window_stop_when_cdp_is_unsupported(self) -> None:
        page = FakePage(cdp=None)

        await abort_pending_navigation(page)  # type: ignore[arg-type]

        assert page.evaluated == ["window.stop()"]

    async def test_stalled_cdp_answer_is_bounded_and_never_touches_the_wedged_page(self) -> None:
        cdp = FakeCdp(send="hang")
        page = FakePage(cdp=cdp, evaluate="hang")

        elapsed = await _elapsed(abort_pending_navigation(page))  # type: ignore[arg-type]

        assert elapsed < _HANG_BOUND_S
        assert cdp.detach_called  # the session is released even though the command never answered
        assert page.evaluated == []  # window.stop() on a wedged page would hang with no bound of its own

    async def test_hanging_detach_is_bounded(self) -> None:
        page = FakePage(cdp=FakeCdp(detach="hang"))

        elapsed = await _elapsed(abort_pending_navigation(page))  # type: ignore[arg-type]

        assert elapsed < _HANG_BOUND_S

    async def test_fallback_evaluate_is_bounded_and_errors_are_swallowed(self) -> None:
        hanging = FakePage(cdp=None, evaluate="hang")
        failing = FakePage(cdp=None, evaluate="raise")

        assert await _elapsed(abort_pending_navigation(hanging)) < _HANG_BOUND_S  # type: ignore[arg-type]
        await abort_pending_navigation(failing)  # type: ignore[arg-type]  # must not raise

    async def test_caller_cancellation_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(page_health, "_ABORT_TIMEOUT_S", 10.0)
        page = FakePage(cdp=FakeCdp(send="hang"))
        task = asyncio.create_task(abort_pending_navigation(page))  # type: ignore[arg-type]
        await asyncio.sleep(_FAST_S)

        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


class TestProbeAlive:
    async def test_healthy_page(self) -> None:
        page = FakePage(cdp=None)

        assert await probe_alive(page)  # type: ignore[arg-type]
        assert page.evaluated == ["1"]

    async def test_closed_page_is_dead(self) -> None:
        page = FakePage(cdp=None, closed=True)

        assert not await probe_alive(page)  # type: ignore[arg-type]

    async def test_failing_evaluate_is_dead(self) -> None:
        page = FakePage(cdp=None, evaluate="raise")

        assert not await probe_alive(page)  # type: ignore[arg-type]

    async def test_hanging_evaluate_is_dead_within_the_bound(self) -> None:
        page = FakePage(cdp=None, evaluate="hang")

        started = time.monotonic()
        alive = await probe_alive(page)  # type: ignore[arg-type]

        assert not alive
        assert time.monotonic() - started < _HANG_BOUND_S


def _browser(session: AsyncMock) -> MagicMock:
    browser = MagicMock()
    browser.new_browser_cdp_session = session
    return browser


async def _hang() -> None:
    await asyncio.Event().wait()


class TestProbeBrowserAlive:
    async def test_answering_browser_is_alive_and_its_session_is_released(self) -> None:
        cdp = FakeCdp()

        assert await probe_browser_alive(_browser(AsyncMock(return_value=cdp)))
        assert cdp.sent == ["Browser.getVersion"]
        assert cdp.detach_called

    async def test_failing_session_reads_as_not_alive(self) -> None:
        assert not await probe_browser_alive(_browser(AsyncMock(side_effect=RuntimeError("no browser session"))))

    async def test_hanging_session_reads_as_not_alive_within_the_bound(self) -> None:
        browser = _browser(AsyncMock(side_effect=_hang))

        started = time.monotonic()
        alive = await probe_browser_alive(browser)

        assert not alive
        assert time.monotonic() - started < _HANG_BOUND_S

    async def test_an_exited_driver_is_conclusive(self) -> None:
        with pytest.raises(DriverClosedError, match="Connection closed while reading from the driver"):
            await probe_browser_alive(_browser(AsyncMock(side_effect=Exception(_DRIVER_GONE))))

    async def test_a_driver_that_exits_after_the_session_opened_still_releases_the_session(self) -> None:
        cdp = MagicMock()
        cdp.send = AsyncMock(side_effect=Exception(_DRIVER_GONE))
        cdp.detach = AsyncMock()

        with pytest.raises(DriverClosedError):
            await probe_browser_alive(_browser(AsyncMock(return_value=cdp)))

        cdp.detach.assert_awaited_once()
