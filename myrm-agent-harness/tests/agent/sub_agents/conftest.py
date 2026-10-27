"""Shared fixtures for sub-agent tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.meta_tools.file_ops.observers.snapshot_observer import (
    get_bound_message_id,
    scoped_message_id,
)
from myrm_agent_harness.agent.middlewares._session_context import (
    set_approval_session,
    set_is_subagent,
    set_subagent_task_id,
)
from myrm_agent_harness.agent.middlewares.completion import completion_guard_state as turn_state
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    _session_loop_guards,
    discard_session_loop_guard,
)
from myrm_agent_harness.core.context_vars import approval_session_var, chat_id_var, scoped_value
from myrm_agent_harness.toolkits.code_execution.executors.execution_evidence import (
    ExecutionEvidence,
    record_execution,
    track_execution,
)
from tests.agent.sub_agents.guard_state_probe import PARENT_TURN, start_run, use_every_guard


@pytest.fixture
def verifier_ran_code() -> Iterator[None]:
    """Report that every verifier round launched a command.

    Verifier rounds in tests run against a fake ``spawn_child`` that never reaches an executor, so the
    execution evidence behind the PASS gate would stay empty. Tests that need real evidence record it
    themselves with ``record_execution()`` instead of using this fixture.
    """

    @contextmanager
    def _executed() -> Iterator[ExecutionEvidence]:
        with track_execution() as evidence:
            record_execution()
            yield evidence

    with patch("myrm_agent_harness.agent.sub_agents._verifier_round.track_execution", _executed):
        yield


@pytest.fixture
def parent_run() -> Iterator[None]:
    """A parent run in progress: its guards are reset and it has done some work."""
    sessions_before = set(_session_loop_guards)
    # ``set_approval_session`` overwrites both session vars; the scopes hand the test's own values back.
    with (
        scoped_value(approval_session_var, approval_session_var.get()),
        scoped_value(chat_id_var, chat_id_var.get()),
        scoped_message_id(get_bound_message_id()),
    ):
        set_approval_session("chat_parent")
        start_run(turn=PARENT_TURN)
        use_every_guard(error="network_blocked")
        yield
        turn_state.reset_run_state()
        for session in set(_session_loop_guards) - sessions_before:
            discard_session_loop_guard(session)
        set_is_subagent(False)
        set_subagent_task_id(None)
