"""A child agent runs inline in its parent's context; its run must not touch the parent's per-run guard state.

Every run begins by resetting the per-run guards in place. A child that reset the objects its parent was
using would wipe the parent's tool-call history, frequency window, turn budget, context budget and
terminal errors, so ``child_run_scope`` hands the child guards of its own and gives the parent's back.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent._internals._agent_helpers import (
    child_run_scope,
    release_child_run_state,
    reset_all_guards,
)
from myrm_agent_harness.agent.middlewares._session_context import (
    get_is_subagent,
    get_subagent_task_id,
    get_terminal_errors,
    set_approval_session,
    set_is_subagent,
    set_subagent_task_id,
)
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _session_loop_guards,
    discard_session_loop_guard,
    get_loop_guard,
)
from myrm_agent_harness.agent.security.guards.context_budget import get_context_budget_guard
from myrm_agent_harness.agent.security.guards.frequency_guard import get_frequency_guard
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintTracker
from myrm_agent_harness.agent.security.guards.tool_turn_budget_guard import get_tool_turn_budget_guard
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.sub_agents.executor import SubagentExecutor
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, SubAgentStatus
from myrm_agent_harness.core.context_vars import approval_session_var, chat_id_var, scoped_value

_MESSAGE = "msg_1"


@dataclass(frozen=True)
class _GuardState:
    """What each per-run guard currently remembers, comparable across a child run."""

    tool_calls: int
    frequency_calls: int
    turn_budget_count: int
    context_tokens: int
    terminal_errors: frozenset[str]


def _state() -> _GuardState:
    return _GuardState(
        tool_calls=len(get_loop_guard()._window),
        frequency_calls=int(get_frequency_guard().get_stats()["current_window_size"]),
        turn_budget_count=get_tool_turn_budget_guard().check("web_search_tool", message_id=_MESSAGE).tool_count,
        context_tokens=get_context_budget_guard().used_tokens,
        terminal_errors=frozenset(get_terminal_errors().get_all()),
    )


def _use_every_guard(*, error: str) -> None:
    """What a run leaves behind in the guards: one tool call, one result, one error category."""
    get_loop_guard().pre_check("file_write_tool", {"path": "app.py"})
    get_frequency_guard().record("file_write_tool")
    get_tool_turn_budget_guard().record("web_search_tool", message_id=_MESSAGE)
    get_context_budget_guard().check_and_truncate("x" * 4_000, "bash_code_execute_tool")
    get_terminal_errors().add(error)


def _start_run(*, is_resume: bool = False) -> None:
    """The reset every run opens with, exactly as ``run_agent_loop`` calls it."""
    reset_all_guards(is_resume=is_resume, graph_recursion_limit=100, unattended_mode=False)


@pytest.fixture(autouse=True)
def _parent_run() -> Iterator[None]:
    """A parent run in progress: its guards are reset and it has done some work."""
    # ``set_approval_session`` overwrites both session vars; the scopes hand the test's own values back.
    with scoped_value(approval_session_var, approval_session_var.get()), scoped_value(chat_id_var, chat_id_var.get()):
        set_approval_session("chat_parent")
        _start_run()
        _use_every_guard(error="network_blocked")
        yield
        release_child_run_state("task_child_1")
        discard_session_loop_guard("chat_parent")
        set_is_subagent(False)
        set_subagent_task_id(None)


def test_a_child_run_leaves_the_parents_guard_state_as_it_found_it() -> None:
    parent = _state()
    parent_guards = (
        get_loop_guard(),
        get_frequency_guard(),
        get_tool_turn_budget_guard(),
        get_context_budget_guard(),
        get_terminal_errors(),
    )
    assert parent.tool_calls == 1 and parent.terminal_errors == {"network_blocked"}

    with child_run_scope("task_child_1"):
        _start_run()
        _use_every_guard(error="sandbox_denied")
        _use_every_guard(error="sandbox_denied")

    assert _state() == parent
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
        _start_run(is_resume=True)

        assert _state() == _GuardState(
            tool_calls=0, frequency_calls=0, turn_budget_count=0, context_tokens=0, terminal_errors=frozenset()
        )


@pytest.mark.parametrize("failure", [RuntimeError("child failed"), asyncio.CancelledError()], ids=["error", "cancel"])
def test_the_parent_gets_its_guards_back_when_the_child_fails_or_is_cancelled(failure: BaseException) -> None:
    parent = _state()

    with pytest.raises(type(failure)), child_run_scope("task_child_1"):
        _start_run()
        _use_every_guard(error="sandbox_denied")
        raise failure

    assert _state() == parent
    assert get_is_subagent() is False


def test_a_child_resumed_after_an_approval_pause_finds_its_own_loop_guard_again() -> None:
    """The loop guard keeps a run's call window across a resume, so a child needs the same guard back."""
    with child_run_scope("task_child_1"):
        _start_run()
        _use_every_guard(error="sandbox_denied")
        _use_every_guard(error="sandbox_denied")
        assert len(get_loop_guard()._window) == 2

    with child_run_scope("task_child_1"):
        _start_run(is_resume=True)
        assert len(get_loop_guard()._window) == 2

    with child_run_scope("task_child_2"):
        _start_run(is_resume=True)
        assert len(get_loop_guard()._window) == 0

    release_child_run_state("task_child_1")
    with child_run_scope("task_child_1"):
        _start_run(is_resume=True)
        assert len(get_loop_guard()._window) == 0


def test_a_finished_child_leaves_nothing_behind_in_the_session_loop_guard_registry() -> None:
    before = dict(_session_loop_guards)

    with child_run_scope("task_child_1"):
        _start_run()
        assert "task_child_1" in _session_loop_guards
    release_child_run_state("task_child_1")

    assert _session_loop_guards == before


def test_a_child_run_does_not_take_over_its_parents_session_loop_guard() -> None:
    """A parent resumed from another context finds its guard by session key, so the key must stay the parent's."""
    parent_guard = get_loop_guard()
    assert _session_loop_guards["chat_parent"] is parent_guard

    with child_run_scope("task_child_1"):
        _start_run()

    assert _session_loop_guards["chat_parent"] is parent_guard


def test_a_child_run_restores_the_markers_its_parent_run_was_under() -> None:
    assert get_is_subagent() is False

    with child_run_scope("task_child_1"):
        assert get_is_subagent() is True
        assert get_subagent_task_id() == "task_child_1"
        _start_run()
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


async def test_the_executor_runs_a_child_in_its_own_scope() -> None:
    """The scope belongs to the executor's attempt, so every delegation path gets it."""
    parent = _state()
    seen: list[tuple[bool, str | None, _GuardState]] = []

    async def child_run(**kwargs: object):
        _start_run()
        _use_every_guard(error="sandbox_denied")
        seen.append((get_is_subagent(), get_subagent_task_id(), _state()))
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
    assert _state() == parent
    assert get_is_subagent() is False
