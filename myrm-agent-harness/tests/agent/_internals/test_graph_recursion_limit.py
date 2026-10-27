"""A run's model rounds map exactly onto the step limit of the graph it runs on.

LangGraph counts one step per node, and every middleware hook is a node of its own, so a round costs the
model and tools nodes plus one node per `before_model`/`after_model` hook. `graph_recursion_limit` reads that
from the compiled graph: a budget of N rounds yields N tool executions, however many hooks the graph has.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.errors import GraphRecursionError

from myrm_agent_harness.agent._internals._agent_helpers import graph_recursion_limit

_BARE_NODES = ("__start__", "model", "tools")


def _graph(*hook_nodes: str) -> SimpleNamespace:
    return SimpleNamespace(nodes={name: object() for name in (*_BARE_NODES, *hook_nodes)})


class TestGraphRecursionLimit:
    def test_a_bare_loop_takes_two_steps_a_round(self) -> None:
        assert graph_recursion_limit(16, _graph()) == 32

    def test_each_round_hook_adds_a_step_per_round(self) -> None:
        graph = _graph("a.before_model", "b.after_model", "c.after_model")
        assert graph_recursion_limit(10, graph) == 10 * (2 + 3)

    def test_run_hooks_are_paid_once_not_every_round(self) -> None:
        graph = _graph("a.before_agent", "a.after_agent", "b.after_model")
        assert graph_recursion_limit(10, graph) == 10 * (2 + 1) + 2

    def test_a_graph_without_nodes_is_a_bare_loop(self) -> None:
        assert graph_recursion_limit(7, None) == 14
        assert graph_recursion_limit(7, object()) == 14

    def test_a_round_is_never_free(self) -> None:
        assert graph_recursion_limit(1, _graph()) == 2


class _EndlessToolCaller(BaseChatModel):
    """Calls the tool after every result and never answers."""

    @property
    def _llm_type(self) -> str:
        return "endless-tool-caller"

    def bind_tools(self, tools: object, **kwargs: object) -> _EndlessToolCaller:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        call = {"name": "work", "args": {}, "id": f"call_{len(messages)}"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])


def _middleware(index: int, hooks: tuple[str, ...]) -> AgentMiddleware:
    """A middleware that defines exactly `hooks` (sync and async), each doing nothing."""

    async def passthrough_async(self: AgentMiddleware, state: object, runtime: object = None) -> None:
        return None

    def passthrough(self: AgentMiddleware, state: object, runtime: object = None) -> None:
        return None

    namespace = {hook: passthrough for hook in hooks} | {f"a{hook}": passthrough_async for hook in hooks}
    return type(f"Hooks{index}", (AgentMiddleware,), namespace)()


_HOOKS = ("before_model", "after_model", "before_agent", "after_agent")


@pytest.mark.parametrize(
    "middlewares",
    [
        pytest.param((), id="no-middleware"),
        pytest.param((("before_model",),) * 3, id="three-before-model"),
        pytest.param((("after_model",),) * 9, id="nine-after-model"),
        pytest.param((("before_agent", "after_agent"),), id="run-hooks-only"),
        pytest.param((_HOOKS,) * 3 + (("after_model",),) * 4, id="mixed"),
    ],
)
@pytest.mark.parametrize("rounds", [1, 2, 5, 16])
@pytest.mark.asyncio
async def test_a_budget_of_n_rounds_runs_the_tools_n_times(
    middlewares: tuple[tuple[str, ...], ...], rounds: int
) -> None:
    executed = 0

    async def work() -> str:
        nonlocal executed
        executed += 1
        return "done"

    tool = StructuredTool.from_function(coroutine=work, name="work", description="Do some work.")
    graph = create_agent(
        _EndlessToolCaller(),
        [tool],
        middleware=[_middleware(index, hooks) for index, hooks in enumerate(middlewares)],
    )

    with pytest.raises(GraphRecursionError):
        await graph.ainvoke(
            {"messages": [HumanMessage("go")]}, {"recursion_limit": graph_recursion_limit(rounds, graph)}
        )

    assert executed == rounds
