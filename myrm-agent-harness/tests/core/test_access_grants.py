"""The run's directory grants are one mutable object, so a grant made in one graph node reaches the next.

LangGraph runs every node in a copy of the context: rebinding a ContextVar in the approval node is never seen by
the tool node, which is why the grants live in an object the run opens once.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextvars import ContextVar
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from myrm_agent_harness.core.context_vars import (
    access_grants_var,
    open_access_grants,
    reachable_access_roots,
    scoped_value,
    session_access_roots_var,
)
from myrm_agent_harness.core.security.types import AccessRoot

DECLARED = AccessRoot(path="/declared", writable=True, source="declared")
SESSION = AccessRoot(path="/session", writable=False, source="path_ask_grant")
ONCE = AccessRoot(path="/once/a.txt", writable=False, source="path_ask_once")


@pytest.fixture(autouse=True)
def _no_open_grants() -> Iterator[None]:
    with scoped_value(access_grants_var, None), scoped_value(session_access_roots_var, ()):
        yield


def test_without_an_open_run_only_the_seeded_session_grants_are_reachable() -> None:
    session_access_roots_var.set((SESSION,))

    assert reachable_access_roots() == (SESSION,)


def test_opening_keeps_the_session_grants_the_host_seeded() -> None:
    session_access_roots_var.set((SESSION,))

    grants = open_access_grants((DECLARED,))

    assert grants.session == (SESSION,)
    assert reachable_access_roots() == (DECLARED, SESSION)


def test_what_one_call_opened_is_reachable_until_it_is_dropped() -> None:
    grants = open_access_grants((DECLARED,))

    grants.once = (ONCE,)
    assert reachable_access_roots() == (DECLARED, ONCE)

    grants.once = ()
    assert reachable_access_roots() == (DECLARED,)


def test_a_second_run_in_the_same_context_keeps_session_grants_but_not_once_grants() -> None:
    first = open_access_grants((DECLARED,))
    first.session = (SESSION,)
    first.once = (ONCE,)

    second = open_access_grants(())

    assert second is not first
    assert second.session == (SESSION,)
    assert second.once == ()
    assert second.declared == ()


class _State(TypedDict):
    seen_by_next_node: tuple[str, ...]


async def test_a_grant_written_in_one_graph_node_reaches_the_next_node() -> None:
    grants = open_access_grants(())
    rebound: ContextVar[tuple[AccessRoot, ...]] = session_access_roots_var

    async def approve(_: _State) -> dict[str, object]:
        grants.once = (ONCE,)
        rebound.set((SESSION,))
        return {}

    async def run_tool(_: _State) -> _State:
        return {"seen_by_next_node": tuple(root.path for root in reachable_access_roots())}

    graph = StateGraph(_State)
    graph.add_node("approve", approve)
    graph.add_node("run_tool", run_tool)
    graph.add_edge(START, "approve")
    graph.add_edge("approve", "run_tool")
    graph.add_edge("run_tool", END)

    result = await graph.compile().ainvoke({"seen_by_next_node": ()})

    assert result["seen_by_next_node"] == ("/once/a.txt",), "the object is shared; a rebound ContextVar is not"


def test_a_nested_run_opens_its_own_grants_and_hands_the_callers_back() -> None:
    from myrm_agent_harness.agent._internals._agent_helpers import isolated_run_guards

    caller = open_access_grants((DECLARED,))
    caller.session = (SESSION,)

    with isolated_run_guards("child-1"):
        child = open_access_grants(())
        child.once = (ONCE,)

        assert child.session == (SESSION,), "a nested run inherits what the session granted"
        assert reachable_access_roots() == (SESSION, ONCE)

    assert access_grants_var.get() is caller
    assert reachable_access_roots() == (DECLARED, SESSION)
