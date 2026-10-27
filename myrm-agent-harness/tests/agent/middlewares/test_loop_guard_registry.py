"""The session registry keeps at most SESSION_LOOP_GUARD_LIMIT guards and drops the least recently used first.

A run reaches its guard through a ContextVar. The registry is only how a later run segment of the same
session finds the guard again: an approval resume starts in a fresh context and has nothing but the session
key. Without a bound, every chat the process ever served kept its last window of tool results until restart.
"""

from __future__ import annotations

import contextvars
from collections.abc import Callable

from myrm_agent_harness.agent.middlewares._session_context import set_approval_session
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import (
    SESSION_LOOP_GUARD_LIMIT,
    _session_loop_guards,
    child_loop_guard,
    get_loop_guard,
    reset_loop_guard,
)
from myrm_agent_harness.agent.security.guards.loop_guard import LoopGuard


def _in_fresh_context[T](session: str, action: Callable[[], T]) -> T:
    """Run `action` the way a new run segment sees the world: no inherited guard, only the session key."""

    def body() -> T:
        set_approval_session(session)
        return action()

    return contextvars.Context().run(body)


def _start_run(session: str, *, is_resume: bool = False) -> LoopGuard:
    def start() -> LoopGuard:
        reset_loop_guard(is_resume=is_resume)
        return get_loop_guard()

    return _in_fresh_context(session, start)


def test_the_registry_never_holds_more_guards_than_the_limit() -> None:
    for index in range(SESSION_LOOP_GUARD_LIMIT + 10):
        _start_run(f"chat_{index}")

    assert len(_session_loop_guards) == SESSION_LOOP_GUARD_LIMIT


def test_the_least_recently_used_session_is_dropped_first() -> None:
    for index in range(SESSION_LOOP_GUARD_LIMIT):
        _start_run(f"chat_{index}")
    _start_run("chat_0")

    _start_run("chat_new")

    assert "chat_0" in _session_loop_guards
    assert "chat_1" not in _session_loop_guards
    assert "chat_new" in _session_loop_guards


def test_a_session_inside_the_limit_gets_its_own_guard_and_call_window_back_on_resume() -> None:
    first = _start_run("chat_a")
    first.pre_check("file_read_tool", {"path": "/work/a.txt"})

    resumed = _start_run("chat_a", is_resume=True)

    assert resumed is first
    assert len(resumed._window) == 1


def test_a_session_dropped_by_the_limit_resumes_with_a_fresh_guard() -> None:
    first = _start_run("chat_old")
    for index in range(SESSION_LOOP_GUARD_LIMIT):
        _start_run(f"chat_{index}")

    resumed = _start_run("chat_old", is_resume=True)

    assert resumed is not first


def test_child_guards_count_against_the_same_limit() -> None:
    for index in range(SESSION_LOOP_GUARD_LIMIT + 5):
        with child_loop_guard(f"task_{index}"):
            pass

    assert len(_session_loop_guards) == SESSION_LOOP_GUARD_LIMIT
