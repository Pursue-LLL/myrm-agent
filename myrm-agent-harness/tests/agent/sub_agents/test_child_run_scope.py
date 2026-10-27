"""A child agent runs inline in its parent's context; its run must not touch the parent's per-run guard state.

Every run begins by resetting the per-run guards in place. A child that reset the objects its parent was
using would wipe the parent's tool-call history, frequency window, turn budget, context budget, terminal
errors and the completion guard's turn state (refusal budget, forced-finish latch, evidence, disclosure),
so ``child_run_scope`` hands the child guards of its own and gives the parent's back.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent._internals._agent_helpers import (
    child_run_scope,
    release_child_run_state,
    reset_all_guards,
)
from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    get_bound_message_id,
)
from myrm_agent_harness.agent.middlewares._session_context import (
    get_is_subagent,
    get_subagent_task_id,
    get_terminal_errors,
    set_approval_session,
)
from myrm_agent_harness.agent.middlewares.completion import completion_guard_state as turn_state
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _session_loop_guards,
    get_loop_guard,
)
from myrm_agent_harness.agent.security.guards.context_budget import get_context_budget_guard
from myrm_agent_harness.agent.security.guards.frequency_guard import get_frequency_guard
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintTracker
from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import get_tool_turn_budget_guard
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.sub_agents.executor import SubagentExecutor
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, SubAgentStatus
from myrm_agent_harness.core.context_vars import approval_session_var
from tests.agent.sub_agents.guard_state_probe import (
    CHILD_TURN,
    PARENT_TURN,
    GuardState,
    guard_state,
    start_run,
    turn_registries,
    use_every_guard,
)

pytestmark = pytest.mark.usefixtures("parent_run")


def test_a_child_run_leaves_the_parents_guard_state_as_it_found_it() -> None:
    parent = guard_state()
    parent_guards = (
        get_loop_guard(),
        get_frequency_guard(),
        get_tool_turn_budget_guard(),
        get_context_budget_guard(),
        get_terminal_errors(),
    )
    assert parent.tool_calls == 1 and parent.terminal_errors == {"network_blocked"}

    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        use_every_guard(error="sandbox_denied")

    assert guard_state() == parent
    assert parent_guards == (
        get_loop_guard(),
        get_frequency_guard(),
        get_tool_turn_budget_guard(),
        get_context_budget_guard(),
        get_terminal_errors(),
    )


def test_a_child_starts_from_empty_guards_even_when_its_run_is_a_resume() -> None:
    """A resume keeps what the guards remember; what they remember must be the child's, not its parent's."""
    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN, is_resume=True)

        assert guard_state() == GuardState(
            tool_calls=0,
            frequency_calls=0,
            turn_budget_count=0,
            context_tokens=0,
            terminal_errors=frozenset(),
            turn_refusals=0,
            turn_forced_finish=False,
            turn_evidence=0,
            turn_tier=None,
        )


@pytest.mark.parametrize("failure", [RuntimeError("child failed"), asyncio.CancelledError()], ids=["error", "cancel"])
def test_the_parent_gets_its_guards_back_when_the_child_fails_or_is_cancelled(failure: BaseException) -> None:
    parent = guard_state()

    with pytest.raises(type(failure)), child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        raise failure

    assert guard_state() == parent
    assert get_is_subagent() is False


def test_a_child_resumed_after_an_approval_pause_finds_its_own_loop_guard_again() -> None:
    """The loop guard keeps a run's call window across a resume, so a child needs the same guard back."""
    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        use_every_guard(error="sandbox_denied")
        assert len(get_loop_guard()._window) == 2

    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN, is_resume=True)
        assert len(get_loop_guard()._window) == 2

    with child_run_scope("task_child_2"):
        start_run(turn=CHILD_TURN, is_resume=True)
        assert len(get_loop_guard()._window) == 0

    release_child_run_state("task_child_1")
    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN, is_resume=True)
        assert len(get_loop_guard()._window) == 0


def test_a_finished_child_leaves_nothing_behind_in_the_session_loop_guard_registry() -> None:
    before = dict(_session_loop_guards)

    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        assert "task_child_1" in _session_loop_guards
    release_child_run_state("task_child_1")

    assert _session_loop_guards == before


def test_a_child_run_does_not_take_over_its_parents_session_loop_guard() -> None:
    """A parent resumed from another context finds its guard by session key, so the key must stay the parent's."""
    parent_guard = get_loop_guard()
    assert _session_loop_guards["chat_parent"] is parent_guard

    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)

    assert _session_loop_guards["chat_parent"] is parent_guard


def test_a_child_run_restores_the_markers_its_parent_run_was_under() -> None:
    assert get_is_subagent() is False

    with child_run_scope("task_child_1"):
        assert get_is_subagent() is True
        assert get_subagent_task_id() == "task_child_1"
        start_run(turn=CHILD_TURN)
        set_approval_session("something_else")

    assert get_is_subagent() is False
    assert get_subagent_task_id() is None
    assert approval_session_var.get() == "chat_parent"


def test_a_child_that_delegates_gives_its_own_markers_back_to_its_parent_child() -> None:
    """A grandchild's run ends inside a child that is still running: the child must still count as a subagent."""
    with child_run_scope("task_child_1"):
        with child_run_scope("task_grandchild_1"):
            assert get_subagent_task_id() == "task_grandchild_1"

        assert get_is_subagent() is True
        assert get_subagent_task_id() == "task_child_1"

    assert get_is_subagent() is False


@pytest.mark.parametrize(
    "failure", [None, RuntimeError("child failed"), asyncio.CancelledError()], ids=["done", "error", "cancel"]
)
def test_a_child_leaves_no_turn_state_of_its_own_behind(failure: BaseException | None) -> None:
    before = turn_registries()

    with contextlib.suppress(RuntimeError, asyncio.CancelledError), child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        if failure is not None:
            raise failure

    assert turn_registries() == before


def test_a_child_cannot_reach_its_parents_turn_before_it_has_bound_its_own() -> None:
    """A run resets the turn state under the id it finds; until its own is bound that is its caller's."""
    parent = guard_state()

    with child_run_scope("task_child_1"):
        reset_all_guards(is_resume=False, round_budget=50, unattended_mode=False)

    assert guard_state() == parent
    assert get_bound_message_id() == PARENT_TURN


def test_children_cannot_push_their_parents_turn_out_of_the_registry() -> None:
    parent_turn = turn_state.current_run_state()

    for index in range(turn_state.RUN_STATE_LIMIT + 1):
        task_id = f"task_child_{index}"
        with child_run_scope(task_id):
            start_run(turn=f"turn_child_{index}")
            use_every_guard(error="sandbox_denied")
        release_child_run_state(task_id)

    assert turn_state.current_run_state() is parent_turn


def test_a_child_that_delegates_keeps_its_own_turn_state_through_its_childs_run() -> None:
    with child_run_scope("task_child_1"):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        child = guard_state()

        with child_run_scope("task_grandchild_1"):
            start_run(turn="turn_grandchild")
            use_every_guard(error="network_blocked")
        release_child_run_state("task_grandchild_1")

        assert guard_state() == child


async def test_the_executor_runs_a_child_in_its_own_scope() -> None:
    """The scope belongs to the executor's attempt, so every delegation path gets it."""
    parent = guard_state()
    seen: list[tuple[bool, str | None, GuardState]] = []

    async def child_run(**kwargs: object):
        start_run(turn=CHILD_TURN)
        use_every_guard(error="sandbox_denied")
        seen.append((get_is_subagent(), get_subagent_task_id(), guard_state()))
        yield {"type": AgentEventType.MESSAGE.value, "data": "done"}

    child_agent = MagicMock()
    child_agent.run = child_run
    child_agent.last_run_stats = MagicMock(token_usage=None)
    child_agent._agent = None
    parent_agent = MagicMock()
    parent_agent._subagent_manager = None
    parent_agent._last_context = {}

    with (
        patch(
            "myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.build_child_agent",
            AsyncMock(return_value=child_agent),
        ),
        patch("myrm_agent_harness.agent.sub_agents.executor_attempt_mixin._parse_handover_state", return_value=None),
        patch(
            "myrm_agent_harness.agent.sub_agents.executor_attempt_mixin._auto_vault_or_truncate",
            side_effect=lambda text, *args, **kwargs: text,
        ),
    ):
        result = await SubagentExecutor()._run_single_attempt(
            task_id="task_child_1",
            agent_type="worker",
            task_description="look around",
            config=SubagentConfig(system_prompt="child", timeout_seconds=60),
            context={},
            tool_registry_getter=lambda: [],
            start_time=0.0,
            parent_tracker=None,
            parent_taint=TaintTracker(),
            parent_agent=parent_agent,
            cancel_flags={},
            children_agents={},
            fire_hook=AsyncMock(),
            hook_event_cls=MagicMock(),
        )

    assert result.status == SubAgentStatus.COMPLETED
    in_child, child_task_id, child_state = seen[0]
    assert (in_child, child_task_id) == (True, "task_child_1")
    assert child_state.tool_calls == 1 and child_state.terminal_errors == {"sandbox_denied"}
    assert guard_state() == parent
    assert get_is_subagent() is False
