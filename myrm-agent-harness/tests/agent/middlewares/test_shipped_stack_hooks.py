"""The middleware stack a BaseAgent ships, compiled into a real LangChain agent graph: which hooks run, and what they return.

``SecurityGuardrailMiddleware`` and the other hook middlewares are unit tested on their own, and the graph tests next to
them build the graph from the bare middleware. Neither goes through ``build_middlewares``, which is what an agent runs.
These tests compile that stack with ``create_agent`` and read what the model is sent and what each hook node returns.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import Field

from myrm_agent_harness.agent._internals._agent_build import build_middlewares, create_registry
from myrm_agent_harness.agent.middlewares._session_context import (
    reset_terminal_errors,
    set_pseudonym_store,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.security.types import PIIAction, PrivacyPolicy, SecurityConfig
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.agent.types import AgentRunStatistics, EngineParams
from myrm_agent_harness.core.security.audit import reset_audit_log
from myrm_agent_harness.core.security.guards.privacy_tracker import reset_privacy_tracker
from myrm_agent_harness.utils.token_economics.budget_guard import BudgetStatus

PHONE = "13812345678"
KEY = "sk-ant-abcdefghijklmnopqrstuvwxyz0123456789"
DANGEROUS = "drop database production;"

# The hooks the shipped graph runs: the nodes whose middleware defines a before_model or an after_model hook.
BEFORE_MODEL_NODES = {
    "BudgetBoundaryMiddleware",
    "SecurityBoundaryMiddleware",
    "SessionAccessMiddleware",
    "SecurityGuardrailMiddleware",
}
AFTER_MODEL_NODES = {
    "ClarificationGuardMiddleware",
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


def _tool_call(call_id: str, name: str = "ping", **args: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"id": call_id, "name": name, "args": args}])


class ScriptedModel(BaseChatModel):
    """Answers from a script and records the messages each call was sent, as ``(type, text)`` pairs."""

    script: list[AIMessage]
    calls: list[list[tuple[str, str]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: object, **kwargs: object) -> ScriptedModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.calls.append([(type(m).__name__, str(m.content)) for m in messages])
        reply = self.script[min(len(self.calls), len(self.script)) - 1]
        return ChatResult(generations=[ChatGeneration(message=reply)])


def _shipped_agent(
    script: list[AIMessage],
    *,
    checkpointer: InMemorySaver | None = None,
    without: Sequence[str] = (),
    engine: EngineParams | None = None,
) -> tuple[ScriptedModel, CompiledStateGraph]:
    """The agent's own middleware stack in a graph, minus the middlewares named in *without*."""
    model = ScriptedModel(script=script)
    middlewares = [m for m in build_middlewares(create_registry(), [], engine) if m.name not in without]
    return model, create_agent(model, tools=[ping, leak, step], middleware=middlewares, checkpointer=checkpointer)


def _config(policy: PrivacyPolicy | None = None) -> SecurityConfig:
    # yolo mode lets the test tool run without an approval interrupt.
    return SecurityConfig(
        yolo_mode_enabled=True,
        yolo_mode_enabled_at=time.time(),
        privacy_policy=policy or PrivacyPolicy(enabled=False),
    )


def _redacting() -> SecurityConfig:
    return _config(PrivacyPolicy(enabled=True, s2_action=PIIAction.REDACT, s3_action=PIIAction.REDACT))


def _texts(call: list[tuple[str, str]], kind: type[BaseMessage]) -> list[str]:
    return [text for name, text in call if name == kind.__name__]


@pytest.fixture(autouse=True)
def _clean_session(tmp_path: Path) -> Iterator[None]:
    RAN.clear()
    reset_terminal_errors()
    reset_audit_log()
    reset_privacy_tracker()
    set_security_config(_config())
    set_workspace_root(str(tmp_path))
    yield
    set_security_config(None)
    set_pseudonym_store(None)
    set_workspace_root("")
    reset_terminal_errors()


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
    set_security_config(_config(PrivacyPolicy(enabled=True, s2_action=action, s3_action=action)))
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
    tracker = SimpleNamespace(
        last_budget_status=BudgetStatus.WARNING,
        budget_checker=SimpleNamespace(get_remaining_budget=lambda: 0.5),
    )
    monkeypatch.setattr("myrm_agent_harness.utils.token_economics.tracker.get_token_tracker", lambda: tracker)
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
    script = [_tool_call(f"c{n}", "step", n=n) for n in range(1, 36)] + [AIMessage(content="done")]
    _, agent = _shipped_agent(script, engine=engine)

    await agent.ainvoke({"messages": [HumanMessage(content="step 35 times")]}, {"recursion_limit": 2000})

    assert len(RAN) == expected_runs


async def test_the_budget_hint_is_added_once_per_run_not_every_round(monkeypatch: pytest.MonkeyPatch) -> None:
    tracker = SimpleNamespace(
        last_budget_status=BudgetStatus.WARNING,
        budget_checker=SimpleNamespace(get_remaining_budget=lambda: 0.5),
    )
    monkeypatch.setattr("myrm_agent_harness.utils.token_economics.tracker.get_token_tracker", lambda: tracker)
    script = [_tool_call(f"c{n}", "step", n=n) for n in range(1, 9)] + [AIMessage(content="done")]
    _, agent = _shipped_agent(script)

    result = await agent.ainvoke({"messages": [HumanMessage(content="step eight times")]}, {"recursion_limit": 500})

    hints = [m for m in result["messages"] if isinstance(m, HumanMessage) and "[BUDGET_HINT]" in str(m.content)]
    assert len(hints) == 1
