"""Stopping a run ends any wait for the person that run is in, and only that run's wait."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Iterator
from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.utils.runtime import cancellation
from myrm_agent_harness.utils.runtime.cancellation import (
    CancellationToken,
    OperationCancelledError,
    set_cancel_token,
)
from myrm_agent_harness.utils.runtime.user_control import (
    ToolRole,
    UserControl,
    UserControlTimeoutError,
    apply_user_control_gate,
)

_STOPPED = "stopped while a person was driving"


@pytest.fixture(autouse=True)
def _fast_poll(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(cancellation, "_POLL_INTERVAL_S", 0.02)
    monkeypatch.setattr(cancellation, "_ABORT_GRACE_S", 0.2)
    yield
    set_cancel_token(None)


def _surface() -> SimpleNamespace:
    control = UserControl()
    return SimpleNamespace(user_control=control, observed_generation=control.generation)


def _gated(
    surface: SimpleNamespace,
    calls: list[str],
    *,
    cancelled_result: str | None,
    in_body: Callable[[], None] | None = None,
) -> BaseTool:
    @tool("act_tool")
    async def act() -> str:
        """Act."""
        calls.append("act")
        if in_body is not None:
            in_body()
        return "done"

    (gated,) = apply_user_control_gate(
        [act],
        surface,
        roles={"act_tool": ToolRole.ACT},
        exempt=frozenset(),
        reobserve_notice="look again",
        cancelled_result=cancelled_result,
    )
    return gated


def _stop_after(token: CancellationToken, seconds: float) -> asyncio.Task[None]:
    async def stop() -> None:
        await asyncio.sleep(seconds)
        token.cancel()

    return asyncio.create_task(stop())


@pytest.mark.asyncio
async def test_stopping_the_run_ends_the_wait_and_leaves_no_waiter_behind() -> None:
    control = UserControl()
    control.acquire()
    token = CancellationToken("req")
    set_cancel_token(token)
    stopper = _stop_after(token, 0.05)

    began = time.monotonic()
    with pytest.raises(OperationCancelledError):
        await control.wait_released(timeout=5.0)

    assert time.monotonic() - began < 2.0
    assert control.held is True
    assert control._waiters == []
    await stopper


@pytest.mark.asyncio
async def test_a_run_stopped_before_it_starts_waiting_does_not_wait_at_all() -> None:
    control = UserControl()
    control.acquire()
    token = CancellationToken("req")
    token.cancel()
    set_cancel_token(token)

    with pytest.raises(OperationCancelledError):
        await asyncio.wait_for(control.wait_released(timeout=5.0), timeout=1.0)
    assert control._waiters == []


@pytest.mark.asyncio
async def test_a_stopped_run_is_not_interrupted_when_nobody_holds_control() -> None:
    control = UserControl()
    token = CancellationToken("req")
    token.cancel()
    set_cancel_token(token)

    await control.wait_released(timeout=0.05)


@pytest.mark.asyncio
async def test_stopping_one_run_leaves_another_runs_wait_alone() -> None:
    control = UserControl()
    control.acquire()
    stopped, waiting = CancellationToken("stopped"), CancellationToken("waiting")

    async def run_with(token: CancellationToken) -> None:
        set_cancel_token(token)
        await control.wait_released(timeout=5.0)

    first = asyncio.create_task(run_with(stopped))
    second = asyncio.create_task(run_with(waiting))
    await asyncio.sleep(0.05)
    stopped.cancel()

    with pytest.raises(OperationCancelledError):
        await asyncio.wait_for(first, timeout=2.0)
    assert not second.done()

    control.release()
    await asyncio.wait_for(second, timeout=2.0)


@pytest.mark.asyncio
async def test_a_wait_that_ends_by_release_still_returns_normally_for_a_run_with_a_token() -> None:
    control = UserControl()
    control.acquire()
    set_cancel_token(CancellationToken("req"))
    waiter = asyncio.create_task(control.wait_released(timeout=5.0))
    await asyncio.sleep(0.05)

    control.release()
    await asyncio.wait_for(waiter, timeout=1.0)
    assert control._waiters == []


@pytest.mark.asyncio
async def test_a_release_from_another_thread_still_wakes_a_waiting_run_that_has_a_token() -> None:
    control = UserControl()
    control.acquire()
    set_cancel_token(CancellationToken("req"))
    waiter = asyncio.create_task(control.wait_released(timeout=5.0))
    await asyncio.sleep(0.05)

    threading.Thread(target=control.release).start()
    await asyncio.wait_for(waiter, timeout=1.0)
    assert control._waiters == []


@pytest.mark.asyncio
async def test_a_wait_cancelled_for_another_reason_leaves_no_waiter_or_task_behind() -> None:
    control = UserControl()
    control.acquire()
    set_cancel_token(CancellationToken("req"))
    waiter = asyncio.create_task(control.wait_released(timeout=5.0))
    await asyncio.sleep(0.05)

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.sleep(0.05)

    assert control._waiters == []
    assert [t for t in asyncio.all_tasks() if t is not asyncio.current_task()] == []


@pytest.mark.asyncio
async def test_a_wait_that_outlasts_its_budget_still_reports_the_timeout_for_a_run_with_a_token() -> None:
    control = UserControl()
    control.acquire()
    set_cancel_token(CancellationToken("req"))

    with pytest.raises(UserControlTimeoutError):
        await control.wait_released(timeout=0.05)
    assert control._waiters == []


@pytest.mark.asyncio
async def test_a_gate_with_a_stopped_result_hands_it_back_instead_of_raising() -> None:
    surface, calls = _surface(), []
    gated = _gated(surface, calls, cancelled_result=_STOPPED)
    surface.user_control.acquire()
    token = CancellationToken("req")
    set_cancel_token(token)
    stopper = _stop_after(token, 0.05)

    result = await asyncio.wait_for(gated.ainvoke({}), timeout=2.0)

    assert result == _STOPPED
    assert calls == []
    assert surface.user_control.held is True
    await stopper


@pytest.mark.asyncio
async def test_a_gate_without_a_stopped_result_lets_the_stop_rise_for_an_outer_boundary() -> None:
    surface, calls = _surface(), []
    gated = _gated(surface, calls, cancelled_result=None)
    surface.user_control.acquire()
    token = CancellationToken("req")
    set_cancel_token(token)
    stopper = _stop_after(token, 0.05)

    with pytest.raises(OperationCancelledError):
        await asyncio.wait_for(gated.ainvoke({}), timeout=2.0)
    assert calls == []
    await stopper


@pytest.mark.asyncio
async def test_a_stop_met_by_the_session_guard_inside_the_tool_gives_the_same_result() -> None:
    surface, calls = _surface(), []

    def takeover_then_stop() -> None:
        # The person took control after the gate let the call through, so the session's own guard was waiting.
        surface.user_control.acquire()
        raise OperationCancelledError("stopped")

    gated = _gated(surface, calls, cancelled_result=_STOPPED, in_body=takeover_then_stop)

    assert await gated.ainvoke({}) == _STOPPED
    assert calls == ["act"]


@pytest.mark.asyncio
async def test_a_stop_unrelated_to_the_person_is_not_reported_as_one() -> None:
    surface, calls = _surface(), []

    def stop_elsewhere() -> None:
        raise OperationCancelledError("elsewhere")

    gated = _gated(surface, calls, cancelled_result=_STOPPED, in_body=stop_elsewhere)

    with pytest.raises(OperationCancelledError):
        await gated.ainvoke({})
    assert calls == ["act"]
