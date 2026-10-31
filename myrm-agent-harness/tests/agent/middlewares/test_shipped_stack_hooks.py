"""The middleware stack a BaseAgent ships, compiled into a real LangChain agent graph: which hooks run, and what they return.

``SecurityGuardrailMiddleware`` and the other hook middlewares are unit tested on their own, and the graph tests next to
them build the graph from the bare middleware. Neither goes through ``build_middlewares``, which is what an agent runs.
These tests compile that stack with ``create_agent`` and read what the model is sent and what each hook node returns.
"""

from __future__ import annotations

import inspect
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    set_canary_token,
    set_pseudonym_store,
    set_security_config,
)
from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy, SecurityConfig
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics, EngineParams
from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus
from tests.support.shipped_graph import ScriptedModel, shipped_agent, shipped_session, yolo_config

PHONE = "13812345678"
KEY = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
DANGEROUS = "drop database production;"
CANARY = "canary-0123456789abcdef"

# The hooks the shipped graph runs: the nodes whose middleware defines a before_model or an after_model hook.
BEFORE_MODEL_NODES = {
    "BudgetBoundaryMiddleware",
    "SecurityBoundaryMiddleware",
    "SessionAccessMiddleware",
    "SecurityGuardrailMiddleware",
}
AFTER_MODEL_NODES = {
    "ClarificationGuardMiddleware",
    "ApprovalEvaluationMiddleware",
    "ToolApprovalMiddleware",
    "CompletionGuard",
    "BudgetBoundaryMiddleware",
    "SecurityGuardrailMiddleware",
}


@tool
def ping() -> str:
    """Answer pong."""
    return "pong"


RAN: list[int] = []


@tool
def step(n: int) -> str:
    """Record that step *n* ran."""
    RAN.append(n)
    return f"step {n} done " + "." * n


@tool
def leak() -> str:
    """Answer with a credential."""
    return f"the key is {KEY}"


@tool
def ask_question_tool(questions: str) -> str:
    """Answer for the user."""
    return "asked"


def _tool_call(call_id: str, name: str = "ping", **args: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": args}])


def _shipped_agent(
    script: list[AIMessage],
    *,
    checkpointer: InMemorySaver | None = None,
    without: Sequence[str] = (),
    engine: EngineParams | None = None,
) -> tuple[ScriptedModel, CompiledStateGraph]:
    return shipped_agent(
        script,
        [ping, leak, step, ask_question_tool],
        checkpointer=checkpointer,
        without=without,
        engine=engine,
    )


def _redacting() -> SecurityConfig:
    return yolo_config(PrivacyPolicy(enabled=True, s2_action=PIIAction.REDACT, s3_action=PIIAction.REDACT))


def _budget_status(monkeypatch: pytest.MonkeyPatch, status: BudgetStatus, remaining: float) -> None:
    tracker = SimpleNamespace(
        last_budget_status=status, budget_checker=SimpleNamespace(get_remaining_budget=lambda: remaining)
    )
    monkeypatch.setattr("myrm_agent_harness.utils.token_economics.tracker.get_token_tracker", lambda: tracker)


def _texts(call: list[tuple[str, str]], kind: type[BaseMessage]) -> list[str]:
    return [text for name, text in call if name == kind.__name__]


@pytest.fixture(autouse=True)
def _clean_session(tmp_path: Path) -> Iterator[None]:
    RAN.clear()
    with shipped_session(tmp_path):
        yield


def test_the_shipped_graph_runs_the_hooks_its_middlewares_define() -> None:
    _, agent = _shipped_agent([AIMessage(content="ok")])

    hooks = [
        name.rsplit(".", 1) for name in agent.get_graph().nodes if name.endswith((".before_model", ".after_model"))
    ]

    assert {node for node, hook in hooks if hook == "before_model"} == BEFORE_MODEL_NODES
    assert {node for node, hook in hooks if hook == "after_model"} == AFTER_MODEL_NODES


async def test_the_model_is_sent_the_boundary_rules_and_the_session_directories_once_per_run() -> None:
    model, agent = _shipped_agent([_tool_call("c1"), AIMessage(content="done")])

    await agent.ainvoke({"messages": [HumanMessage(content="call ping")]})

    assert len(model.calls) == 2
    for call in model.calls:
        systems = _texts(call, SystemMessage)
        assert sum("<data_boundary_rules" in text for text in systems) == 1
        assert sum("<session-access>" in text for text in systems) == 1
    first = [name for name, _ in model.calls[0]]
    assert first.index("HumanMessage") < first.index("SystemMessage")


@pytest.mark.parametrize("action", [PIIAction.REDACT, PIIAction.PSEUDONYMIZE, PIIAction.BLOCK])
async def test_pii_in_the_user_input_never_reaches_the_model(action: PIIAction, tmp_path: Path) -> None:
    from myrm_agent_harness.agent.security.detection.pseudonym_store import PseudonymStore

    store = PseudonymStore(str(tmp_path / "pseudonyms.db"))
    set_pseudonym_store(store)
    set_security_config(yolo_config(PrivacyPolicy(enabled=True, s2_action=action, s3_action=action)))
    model, agent = _shipped_agent([AIMessage(content="noted")])

    try:
        await agent.ainvoke({"messages": [HumanMessage(content=f"my phone is {PHONE}, remember it")]})
    finally:
        store.close()

    sent = _texts(model.calls[0], HumanMessage)
    assert PHONE not in str(model.calls)
    if action is PIIAction.BLOCK:
        assert sent[0].startswith("[BLOCKED]")
    if action is PIIAction.PSEUDONYMIZE:
        assert "<PHONE_NUMBER_" in sent[0]


async def test_a_credential_in_a_tool_result_never_reaches_the_model() -> None:
    model, agent = _shipped_agent([_tool_call("c1", "leak"), AIMessage(content="done")])

    await agent.ainvoke({"messages": [HumanMessage(content="call leak")]})

    assert KEY not in str(model.calls)
    assert "[REDACTED:" in _texts(model.calls[1], ToolMessage)[0]


async def test_the_budget_hint_is_the_runtimes_and_is_not_screened_as_the_users_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _budget_status(monkeypatch, BudgetStatus.WARNING, 0.5)
    model, agent = _shipped_agent([AIMessage(content="noted")])

    await agent.ainvoke({"messages": [HumanMessage(content=DANGEROUS)]})

    humans = _texts(model.calls[0], HumanMessage)
    assert humans[0].startswith("[SAFETY_CAUTION:")
    assert "[BUDGET_HINT]" in humans[1]
    assert "[SAFETY_CAUTION:" not in humans[1]


async def _turn_two_updates(agent: CompiledStateGraph, thread: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    async for chunk in agent.astream(
        {"messages": [HumanMessage(content=f"my phone is {PHONE}, ping again")]}, thread, stream_mode="updates"
    ):
        chunks.append(chunk)
    return chunks


async def _announced_calls(chunks: list[dict[str, object]]) -> list[str]:
    """The tool_call_id of every task step the stream layer emits for these updates."""
    ids: list[str] = []
    stats = AgentRunStatistics()
    for chunk in chunks:
        async for event in process_updates_chunk(chunk, stats, "m1"):  # type: ignore[arg-type]
            if event["type"] == AgentEventType.TASKS_STEPS.value:
                ids.append(str(event["tool_call_id"]))
    return ids


@pytest.mark.parametrize("upgraded", [False, True], ids=["same_graph", "thread_from_a_graph_without_the_hooks"])
async def test_a_hook_hands_back_what_it_changed_not_the_whole_thread(upgraded: bool) -> None:
    set_security_config(_redacting())
    saver = InMemorySaver()
    thread = {"configurable": {"thread_id": "t1"}}
    hookless = tuple(BEFORE_MODEL_NODES) if upgraded else ()
    _, first_agent = _shipped_agent(
        [_tool_call("old1"), AIMessage(content="first done")], checkpointer=saver, without=hookless
    )
    await first_agent.ainvoke({"messages": [HumanMessage(content="call ping")]}, thread)
    model, agent = _shipped_agent([_tool_call("new1"), AIMessage(content="second done")], checkpointer=saver)

    chunks = await _turn_two_updates(agent, thread)

    guard_updates = [u for chunk in chunks if (u := chunk.get("SecurityGuardrailMiddleware.before_model"))]
    assert [len(update["messages"]) for update in guard_updates] == [1]
    assert PHONE not in str(model.calls)
    assert await _announced_calls(chunks) == ["new1"]


@pytest.mark.parametrize(
    ("engine", "expected_runs"),
    [(None, 35), (EngineParams(max_tool_calls=3), 3), (EngineParams(max_bash_calls=1), 35)],
    ids=["no_cap_by_default", "total_cap", "bash_cap_leaves_other_tools_alone"],
)
async def test_a_tool_call_cap_applies_only_when_it_is_configured(
    engine: EngineParams | None, expected_runs: int
) -> None:
    """35 calls is more than the 30 the engine once defaulted to; with no cap configured every one of them runs."""
    script = [_tool_call(f"c{n}", "step", n=n) for n in range(1, 36)]
    script.append(AIMessage(content="done"))
    _, agent = _shipped_agent(script, engine=engine)

    await agent.ainvoke({"messages": [HumanMessage(content="step 35 times")]}, {"recursion_limit": 2000})

    assert len(RAN) == expected_runs


async def test_the_budget_hint_is_added_once_per_run_not_every_round(monkeypatch: pytest.MonkeyPatch) -> None:
    _budget_status(monkeypatch, BudgetStatus.WARNING, 0.5)
    script = [_tool_call(f"c{n}", "step", n=n) for n in range(1, 9)] + [AIMessage(content="done")]
    _, agent = _shipped_agent(script)

    result = await agent.ainvoke({"messages": [HumanMessage(content="step eight times")]}, {"recursion_limit": 500})

    hints = [m for m in result["messages"] if isinstance(m, HumanMessage) and "[BUDGET_HINT]" in str(m.content)]
    assert len(hints) == 1


def _defined_hooks(middlewares: Sequence[AgentMiddleware]) -> Iterator[tuple[AgentMiddleware, str, str]]:
    """``(middleware, node, method)`` for each before/after_model method a middleware overrides, as create_agent reads it."""
    for m in middlewares:
        for node in ("before_model", "after_model"):
            for method in (node, f"a{node}"):
                if getattr(type(m), method) is not getattr(AgentMiddleware, method):
                    yield m, node, method


def _counted(method: Callable[..., object], node: str, calls: Counter[str]) -> Callable[..., object]:
    if inspect.iscoroutinefunction(method):

        async def acounted(state: dict[str, object], runtime: object) -> object:
            calls[node] += 1
            return await method(state, runtime)

        return acounted

    def counted(state: dict[str, object], runtime: object) -> object:
        calls[node] += 1
        return method(state, runtime)

    return counted


async def test_every_hook_the_shipped_stack_defines_runs_once_per_model_round() -> None:
    """A middleware that joins the stack with a hook is covered here without a line changed in this file."""
    middlewares = build_middlewares(create_registry(), [], None)
    declared = {f"{m.name}.{node}" for m, node, _ in _defined_hooks(middlewares)}
    calls: Counter[str] = Counter()
    # create_agent takes the nodes from the class and binds the callables from the instance: counting wraps the latter.
    for m, node, method in _defined_hooks(middlewares):
        setattr(m, method, _counted(getattr(m, method), f"{m.name}.{node}", calls))
    model = ScriptedModel(script=[_tool_call("c1"), AIMessage(content="done")])
    agent = create_agent(model, tools=[ping, leak, step], middleware=middlewares)

    await agent.ainvoke({"messages": [HumanMessage(content="call ping")]})

    assert {name for name in agent.get_graph().nodes if name.endswith((".before_model", ".after_model"))} == declared
    assert len(model.calls) == 2
    assert dict(calls) == dict.fromkeys(declared, 2)


async def test_a_tool_call_that_needs_approval_stops_at_the_approval_hook() -> None:
    set_security_config(SecurityConfig(yolo_mode_enabled=False, privacy_policy=PrivacyPolicy(enabled=False)))
    _, agent = _shipped_agent([_tool_call("c1", "step", n=1), AIMessage(content="done")], checkpointer=InMemorySaver())

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content="step once")]}, {"configurable": {"thread_id": "t"}}
    )

    assert result["__interrupt__"]
    assert RAN == []


async def test_a_canary_token_the_model_repeats_is_scrubbed_from_its_reply() -> None:
    set_canary_token(CANARY)
    _, agent = _shipped_agent([AIMessage(content=f"the secret is {CANARY}")])

    result = await agent.ainvoke({"messages": [HumanMessage(content="hello")]})

    assert CANARY not in str(result["messages"][-1].content)


async def test_a_tool_call_made_once_the_budget_is_spent_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    _budget_status(monkeypatch, BudgetStatus.FINALIZATION, 0.0)
    model, agent = _shipped_agent([_tool_call("c1", "step", n=1), AIMessage(content="not reached")])

    result = await agent.ainvoke({"messages": [HumanMessage(content="step once")]})

    assert RAN == []
    assert len(model.calls) == 1
    assert not result["messages"][-1].tool_calls


async def test_a_tool_called_next_to_ask_question_tool_is_blocked() -> None:
    calls = [
        {"id": "q1", "name": "ask_question_tool", "args": {"questions": "which?"}},
        {"id": "s1", "name": "step", "args": {"n": 1}},
    ]
    _, agent = _shipped_agent([AIMessage(content="", tool_calls=calls), AIMessage(content="done")])

    result = await agent.ainvoke({"messages": [HumanMessage(content="ask and step")]})

    blocked = [m for m in result["messages"] if isinstance(m, ToolMessage) and m.status == "error"]
    assert RAN == []
    assert [m.tool_call_id for m in blocked] == ["s1"]
