"""UserControl truth and the tool gate: a held control stops every tool, and a stale plan never executes."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool, StructuredTool, tool

from myrm_agent_harness.utils.runtime.user_control import (
    RoleOf,
    ToolRole,
    UserControl,
    UserControlTimeoutError,
    apply_user_control_gate,
    get_user_control,
    plan_is_stale,
    planned_against,
)

_NOTICE = "re-observe first"


class _Surface(SimpleNamespace):
    user_control: UserControl
    observed_generation: int


def _surface() -> _Surface:
    control = UserControl()
    return _Surface(user_control=control, observed_generation=control.generation)


_ROLES: dict[str, RoleOf] = {"look_tool": ToolRole.OBSERVE, "act_tool": ToolRole.ACT}


def _tools(calls: list[str]) -> list[BaseTool]:
    @tool("look_tool")
    async def look() -> str:
        """Observe."""
        calls.append("look")
        return "page"

    @tool("act_tool")
    async def act() -> str:
        """Act."""
        calls.append("act")
        return "done"

    @tool("ask_tool")
    async def ask() -> str:
        """Exempt."""
        calls.append("ask")
        return "asked"

    @tool("misc_tool")
    async def misc() -> str:
        """Neither observing nor acting."""
        calls.append("misc")
        return "misc"

    return [look, act, ask, misc]


def _gate(
    surface: _Surface,
    tools: list[BaseTool],
    *,
    roles: dict[str, RoleOf] | None = None,
    exempt: frozenset[str] = frozenset({"ask_tool"}),
    timeout_s: float = 1.0,
) -> dict[str, BaseTool]:
    apply_user_control_gate(
        tools,
        surface,
        roles=_ROLES if roles is None else roles,
        exempt=exempt,
        reobserve_notice=_NOTICE,
        wait_timeout_s=timeout_s,
        timeout_error=lambda seconds: TimeoutError(f"gave up after {seconds}"),
    )
    return {t.name: t for t in tools}


# --- UserControl ---------------------------------------------------------------------------------


def test_acquire_and_release_are_idempotent_and_count_generations() -> None:
    control = UserControl()
    assert control.release() is False
    assert control.generation == 0
    assert control.acquire() is True
    assert control.acquire() is False
    assert control.held is True
    assert control.release() is True
    assert (control.held, control.generation) == (False, 1)
    assert control.release() is False
    assert control.generation == 1


def test_process_control_is_a_single_instance() -> None:
    assert get_user_control() is get_user_control()


@pytest.mark.asyncio
async def test_wait_released_returns_immediately_when_nobody_holds() -> None:
    await asyncio.wait_for(UserControl().wait_released(timeout=0.0), timeout=0.5)


@pytest.mark.asyncio
async def test_wait_released_wakes_every_waiter_on_release() -> None:
    control = UserControl()
    control.acquire()
    waiters = [asyncio.create_task(control.wait_released(timeout=2.0)) for _ in range(3)]
    await asyncio.sleep(0.02)
    assert not any(w.done() for w in waiters)
    control.release()
    await asyncio.wait_for(asyncio.gather(*waiters), timeout=1.0)
    assert control._waiters == []


@pytest.mark.asyncio
async def test_release_still_wakes_live_waiters_when_one_waiter_loop_is_closed() -> None:
    control = UserControl()
    control.acquire()
    dead_loop = asyncio.new_event_loop()
    control._waiters.append(dead_loop.create_future())
    dead_loop.close()
    live = asyncio.create_task(control.wait_released(timeout=2.0))
    await asyncio.sleep(0.02)
    assert control.release() is True
    await asyncio.wait_for(live, timeout=1.0)


@pytest.mark.asyncio
async def test_wait_released_times_out_and_leaves_no_waiter_behind() -> None:
    control = UserControl()
    control.acquire()
    with pytest.raises(UserControlTimeoutError) as info:
        await control.wait_released(timeout=0.05)
    assert info.value.timeout_seconds == 0.05
    assert control.held is True
    assert control._waiters == []


@pytest.mark.asyncio
async def test_cancelled_waiter_is_removed() -> None:
    control = UserControl()
    control.acquire()
    task = asyncio.create_task(control.wait_released(timeout=5.0))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert control._waiters == []


@pytest.mark.asyncio
async def test_release_from_another_thread_wakes_the_waiting_loop() -> None:
    control = UserControl()
    control.acquire()
    waiter = asyncio.create_task(control.wait_released(timeout=2.0))
    await asyncio.sleep(0.02)
    threading.Thread(target=control.release).start()
    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_a_waiter_survives_release_followed_by_immediate_reacquire() -> None:
    control = UserControl()
    control.acquire()
    waiter = asyncio.create_task(control.wait_released(timeout=0.3))
    await asyncio.sleep(0.02)
    control.release()
    control.acquire()
    # The person took control again before the waiter ran: it must keep waiting, not slip through.
    with pytest.raises(UserControlTimeoutError):
        await waiter


# --- gate ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_is_transparent_while_nobody_holds_control() -> None:
    calls: list[str] = []
    surface = _surface()
    tools = _gate(surface, _tools(calls))
    assert await tools["act_tool"].ainvoke({}) == "done"
    assert await tools["look_tool"].ainvoke({}) == "page"
    assert calls == ["act", "look"]


@pytest.mark.asyncio
async def test_held_control_stops_every_tool_but_the_exempt_one() -> None:
    calls: list[str] = []
    surface = _surface()
    tools = _gate(surface, _tools(calls))
    surface.user_control.acquire()

    assert await tools["ask_tool"].ainvoke({}) == "asked"
    pending = [asyncio.create_task(tools[name].ainvoke({})) for name in ("look_tool", "act_tool", "misc_tool")]
    await asyncio.sleep(0.05)
    assert not any(p.done() for p in pending)
    assert calls == ["ask"]

    surface.user_control.release()
    results = await asyncio.wait_for(asyncio.gather(*pending), timeout=1.0)
    # The observing and neutral tools run; the acting call refuses although the observation finished first,
    # because it was planned before the person touched the surface and the model has not seen that observation.
    assert results == ["page", _NOTICE, "misc"]
    assert calls == ["ask", "look", "misc"]


@pytest.mark.asyncio
async def test_acting_tool_runs_again_only_after_a_successful_observation() -> None:
    calls: list[str] = []
    surface = _surface()
    tools = _gate(surface, _tools(calls))
    surface.user_control.acquire()
    surface.user_control.release()

    assert await tools["act_tool"].ainvoke({}) == _NOTICE
    assert await tools["misc_tool"].ainvoke({}) == "misc"
    assert await tools["act_tool"].ainvoke({}) == _NOTICE
    assert await tools["look_tool"].ainvoke({}) == "page"
    assert await tools["act_tool"].ainvoke({}) == "done"
    assert calls == ["misc", "look", "act"]


@pytest.mark.asyncio
async def test_control_taken_during_an_observation_keeps_it_stale() -> None:
    surface = _surface()

    @tool("look_tool")
    async def look() -> str:
        """Observe while the person takes control and hands it back."""
        surface.user_control.acquire()
        surface.user_control.release()
        return "page"

    @tool("act_tool")
    async def act() -> str:
        """Act."""
        return "done"

    gated = _gate(surface, [look, act], exempt=frozenset())
    assert await gated["look_tool"].ainvoke({}) == "page"
    assert await gated["act_tool"].ainvoke({}) == _NOTICE


@pytest.mark.asyncio
async def test_failed_observation_does_not_clear_staleness() -> None:
    surface = _surface()

    @tool("look_tool")
    async def look() -> str:
        """Observe, but fail."""
        raise RuntimeError("page crashed")

    @tool("act_tool")
    async def act() -> str:
        """Act."""
        return "done"

    gated = _gate(surface, [look, act], exempt=frozenset())
    surface.user_control.acquire()
    surface.user_control.release()
    with pytest.raises(RuntimeError):
        await gated["look_tool"].ainvoke({})
    assert await gated["act_tool"].ainvoke({}) == _NOTICE


@pytest.mark.asyncio
async def test_a_tool_that_both_looks_and_acts_takes_its_role_from_the_call() -> None:
    surface = _surface()

    @tool("vision_tool")
    async def vision(action: str) -> str:
        """Capture or click."""
        return f"did {action}"

    gated = _gate(
        surface,
        [vision],
        exempt=frozenset(),
        roles={"vision_tool": lambda kwargs: ToolRole.OBSERVE if kwargs["action"] == "capture" else ToolRole.ACT},
    )
    surface.user_control.acquire()
    surface.user_control.release()

    assert await gated["vision_tool"].ainvoke({"action": "click"}) == _NOTICE
    assert await gated["vision_tool"].ainvoke({"action": "capture"}) == "did capture"
    assert await gated["vision_tool"].ainvoke({"action": "click"}) == "did click"


@pytest.mark.asyncio
async def test_gate_converts_the_wait_timeout_into_the_toolkit_error() -> None:
    surface = _surface()
    tools = _gate(surface, _tools([]), timeout_s=0.05)
    surface.user_control.acquire()
    with pytest.raises(TimeoutError, match=r"gave up after 0\.05"):
        await tools["look_tool"].ainvoke({})


@pytest.mark.asyncio
async def test_gate_raises_the_control_timeout_when_no_toolkit_error_is_given() -> None:
    surface = _surface()
    tools = _tools([])
    apply_user_control_gate(
        tools, surface, roles=_ROLES, exempt=frozenset({"ask_tool"}), reobserve_notice=_NOTICE, wait_timeout_s=0.05
    )
    surface.user_control.acquire()
    with pytest.raises(UserControlTimeoutError, match="action was not run"):
        await tools[0].ainvoke({})


def test_gate_rejects_names_that_match_no_tool() -> None:
    with pytest.raises(ValueError, match="ghost_tool"):
        apply_user_control_gate(
            _tools([]),
            _surface(),
            roles={"ghost_tool": ToolRole.OBSERVE},
            exempt=frozenset(),
            reobserve_notice=_NOTICE,
        )


def test_gate_rejects_a_tool_without_coroutine() -> None:
    def sync_only() -> str:
        return "x"

    sync_tool = StructuredTool.from_function(func=sync_only, name="sync_tool", description="sync")
    with pytest.raises(TypeError, match="sync_tool"):
        apply_user_control_gate([sync_tool], _surface(), roles={}, exempt=frozenset(), reobserve_notice=_NOTICE)


def test_a_plan_is_stale_once_control_changed_hands_after_it_was_made() -> None:
    control = UserControl()

    with planned_against(control.generation):
        assert plan_is_stale(control) is False
        control.acquire()
        assert plan_is_stale(control) is False, "a person who still holds control has not changed anything yet"
        control.release()
        assert plan_is_stale(control) is True


def test_a_plan_made_after_the_hand_over_is_not_stale() -> None:
    control = UserControl()
    control.acquire()
    control.release()

    with planned_against(control.generation):
        assert plan_is_stale(control) is False


def test_nothing_is_stale_outside_a_plan() -> None:
    control = UserControl()
    control.acquire()
    control.release()

    assert plan_is_stale(control) is False
    with planned_against(0):
        pass
    assert plan_is_stale(control) is False, "leaving the plan must forget it"


@pytest.mark.asyncio
async def test_a_plan_binds_only_the_task_that_made_it() -> None:
    control = UserControl()
    entered, finished = asyncio.Event(), asyncio.Event()

    async def planner() -> None:
        with planned_against(control.generation):
            entered.set()
            await finished.wait()

    task = asyncio.create_task(planner())
    await entered.wait()
    control.acquire()
    control.release()

    assert plan_is_stale(control) is False
    finished.set()
    await task
