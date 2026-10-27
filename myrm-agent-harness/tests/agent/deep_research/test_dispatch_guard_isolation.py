"""Research agents run in parallel inside the orchestrator's run; none of them may touch another run's guards.

Every run begins by resetting the per-run guards it finds, in place. Research agents that shared the guards of
the run that dispatched them would erase that run's tool-call history and budgets whenever one of them
started, and would count each other's tool calls as their own, so a looping agent broke later than it should.
The tests drive the real ``_dispatch_research_agents`` with research agents that open their run the way
``run_agent_loop`` does: bind the session from their context, then reset the guards.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.deep_research.orchestrator import DeepResearchOrchestrator
from myrm_agent_harness.agent.middlewares._session_context import (
    get_is_subagent,
    get_terminal_errors,
    set_approval_session,
)
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _session_loop_guards,
    get_loop_guard,
)
from myrm_agent_harness.agent.security.guards.context_budget import get_context_budget_guard
from myrm_agent_harness.agent.security.guards.frequency_guard import get_frequency_guard
from myrm_agent_harness.agent.security.guards.loop_guard import LoopAction
from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import get_tool_turn_budget_guard
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.core.context_vars import approval_session_var
from tests.agent.sub_agents.guard_state_probe import guard_state, start_run, use_every_guard

pytestmark = pytest.mark.usefixtures("parent_run")

_PARENT_SESSION = "chat_parent"
_BREAK_AT = 10  # identical calls a LoopGuard allows before it breaks the loop


class _ResearchAgent:
    """A research agent whose run opens like the real one and then does `work`."""

    def __init__(self, turn: str, work: Callable[[], Awaitable[None]]) -> None:
        self._turn = turn
        self._work = work

    async def run(
        self,
        query: str,
        chat_history: list[object],
        context: dict[str, object],
        cancel_token: object,
    ) -> AsyncIterator[dict[str, object]]:
        set_approval_session(str(context.get("approval_session_key") or context.get("session_id") or ""))
        start_run(turn=self._turn)
        await self._work()
        yield {"type": AgentEventType.MESSAGE.value, "data": f"findings of {query}"}


def _guards() -> tuple[object, ...]:
    return (
        get_loop_guard(),
        get_frequency_guard(),
        get_tool_turn_budget_guard(),
        get_context_budget_guard(),
        get_terminal_errors(),
    )


async def _dispatch(agents: dict[str, _ResearchAgent]) -> list[str]:
    orchestrator = DeepResearchOrchestrator(llm=MagicMock(model_name="gpt-4o"), parent_tools=[])
    orchestrator._start_time = 1.0
    orchestrator._context = {"session_id": _PARENT_SESSION}
    assert orchestrator._config.max_concurrent_agents == 3  # the late agent below waits for a free slot
    with (
        patch(
            "myrm_agent_harness.agent.sub_agents.builder.build_standalone_agent",
            side_effect=lambda **kwargs: agents[kwargs["task_description"]],
        ),
        patch("myrm_agent_harness.agent.sub_agents.builder.filter_tools", return_value=[]),
    ):
        return await orchestrator._dispatch_research_agents(
            tasks=[{"task": name, "tc_id": f"tc_{index}"} for index, name in enumerate(agents)],
            message_id="msg_research",
        )


async def _use_every_guard() -> None:
    use_every_guard(error="sandbox_denied")


@pytest.mark.asyncio
async def test_research_agents_leave_the_dispatching_runs_guard_state_as_it_found_it() -> None:
    parent = guard_state()
    parent_guards = _guards()
    assert parent.tool_calls == 1 and parent.terminal_errors == {"network_blocked"}

    await _dispatch({name: _ResearchAgent(f"turn_{name}", _use_every_guard) for name in ("a", "b", "c")})

    assert guard_state() == parent
    assert _guards() == parent_guards


@pytest.mark.asyncio
async def test_concurrent_research_agents_each_run_on_guards_of_their_own() -> None:
    parent_guards = _guards()
    barrier = asyncio.Barrier(3)
    seen: list[tuple[object, ...]] = []

    async def meet_and_look() -> None:
        await barrier.wait()  # every agent has opened its run (and reset its guards) by now
        seen.append(_guards())

    await _dispatch({name: _ResearchAgent(f"turn_{name}", meet_and_look) for name in ("a", "b", "c")})

    assert len(seen) == 3
    for kind in range(len(parent_guards)):
        assert len({id(guards[kind]) for guards in (*seen, parent_guards)}) == 4


@pytest.mark.asyncio
async def test_a_research_agent_keeps_the_session_it_was_dispatched_under() -> None:
    inside: list[tuple[str | None, bool]] = []

    async def look() -> None:
        inside.append((approval_session_var.get(), get_is_subagent()))

    await _dispatch({"a": _ResearchAgent("turn_a", look)})

    assert inside == [(_PARENT_SESSION, False)]
    assert approval_session_var.get() == _PARENT_SESSION


async def _calls_until_the_loop_breaks(*, started_late: bool) -> int:
    """How many identical calls a looping research agent makes before its own guard breaks the loop.

    With `started_late`, siblings open their runs while the looper is mid-loop: one of them begins only
    after another finished, the way the fourth of four tasks waits for a free slot.
    """
    looper_halfway, late_agent_started = asyncio.Event(), asyncio.Event()
    calls: list[int] = []

    async def loop() -> None:
        made = 0
        for _ in range(_BREAK_AT // 2):
            get_loop_guard().pre_check("web_fetch_tool", {"url": "https://a.test"})
            made += 1
        looper_halfway.set()
        if started_late:
            await late_agent_started.wait()
        while made < 5 * _BREAK_AT:
            made += 1
            if get_loop_guard().pre_check("web_fetch_tool", {"url": "https://a.test"}).action is LoopAction.BREAK:
                break
        calls.append(made)

    async def finish_once_the_looper_is_halfway() -> None:
        await looper_halfway.wait()

    async def finish_once_the_late_agent_started() -> None:
        await late_agent_started.wait()

    async def open_and_signal() -> None:
        late_agent_started.set()

    agents = {"looper": _ResearchAgent("turn_looper", loop)}
    if started_late:
        agents |= {
            "early": _ResearchAgent("turn_early", finish_once_the_looper_is_halfway),
            "holder": _ResearchAgent("turn_holder", finish_once_the_late_agent_started),
            "late": _ResearchAgent("turn_late", open_and_signal),
        }
    await _dispatch(agents)
    return calls[0]


@pytest.mark.asyncio
async def test_a_looping_research_agent_breaks_at_its_own_threshold_whatever_its_siblings_do() -> None:
    alone = await _calls_until_the_loop_breaks(started_late=False)
    beside_siblings = await _calls_until_the_loop_breaks(started_late=True)

    assert alone == _BREAK_AT
    assert beside_siblings == alone


@pytest.mark.asyncio
async def test_research_agents_leave_nothing_in_the_loop_guard_registry_even_when_one_fails() -> None:
    registry = dict(_session_loop_guards)
    assert registry[_PARENT_SESSION] is get_loop_guard()

    async def explode() -> None:
        raise RuntimeError("research backend down")

    await _dispatch(
        {"fine": _ResearchAgent("turn_fine", _use_every_guard), "broken": _ResearchAgent("turn_broken", explode)}
    )

    assert dict(_session_loop_guards) == registry
