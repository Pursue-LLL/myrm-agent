"""The user's instructions and the memory block in one model call, mounted in the factory's order.

[INPUT]
- app/ai_agents/general_agent/factory/ (POS: source under inspection)
- app/ai_agents/agent_middlewares/user_instructions_middleware.py (POS: injects <user_instructions> unless that tag is already among the leading system messages)
- myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware (POS: injects <user_memory_context> into every model call)

[OUTPUT]
- Tests that the factory mounts the instructions middleware before the memory middleware and that, in that order, every model call carries each block exactly once.

[POS]
The memory block names ``<user_instructions>`` when it says which instructions take precedence, and the instructions
middleware decides whether its own block is already there by looking for that tag in the leading system messages.
Mounted behind the memory middleware it reads the mention as its own block and injects nothing, so the user's
instructions never reach the model. The factory's order is part of the contract between the two.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from myrm_agent_harness.agent.middlewares.memory_context.memory_context_middleware import memory_context_middleware
from myrm_agent_harness.agent.skill_agent.context import set_memory_manager
from myrm_agent_harness.toolkits.memory.config import RecallMode
from pydantic import Field

from app.ai_agents.agent_middlewares.user_instructions_middleware import user_instructions_middleware

FACTORY_PATH = Path(__file__).resolve().parents[3] / "app" / "ai_agents" / "general_agent" / "factory" / "middlewares.py"

_IDENTITY = "<identity>You are the test agent.</identity>"
_INSTRUCTIONS = "Always answer in French."
_INSTRUCTIONS_TAG = "<user_instructions"
_MEMORY_TAG = "<user_memory_context"
_BY_NAME: dict[str, AgentMiddleware] = {
    "user_instructions_middleware": user_instructions_middleware,
    "memory_context_middleware": memory_context_middleware,
}


def _mounted_pair() -> list[str]:
    """Names of the two middlewares in the order the factory's `middlewares_list = [...]` literal mounts them."""
    tree = ast.parse(FACTORY_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        is_list_assignment = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "middlewares_list" for target in node.targets
        )
        if is_list_assignment and isinstance(node.value, ast.List):
            names = [element.id for element in node.value.elts if isinstance(element, ast.Name)]
            return [name for name in names if name in _BY_NAME]
    raise AssertionError("factory.py does not assign a `middlewares_list` literal")


class _RecordingModel(BaseChatModel):
    """Answers "ok" and records the messages each call was sent, as ``(type, text)`` pairs."""

    calls: list[list[tuple[str, str]]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "recording"

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        self.calls.append([(type(m).__name__, str(m.content)) for m in messages])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


@pytest.fixture
def memory_manager() -> Iterator[MagicMock]:
    manager = MagicMock()
    manager.recall_mode = RecallMode.HYBRID
    manager.user_id = "u1"
    set_memory_manager(manager)
    try:
        yield manager
    finally:
        set_memory_manager(None)


def _system_positions(call: list[tuple[str, str]], tag: str) -> list[int]:
    return [i for i, (kind, text) in enumerate(call) if kind == "SystemMessage" and text.lstrip().startswith(tag)]


def test_the_factory_mounts_the_instructions_before_the_memory_block() -> None:
    assert _mounted_pair() == ["user_instructions_middleware", "memory_context_middleware"], (
        "the memory block mentions <user_instructions>; mounted first, it makes the instructions middleware believe "
        "its block is already present, and the user's instructions are never injected"
    )


async def test_every_model_call_carries_the_instructions_and_the_memory_block_once(memory_manager: MagicMock) -> None:
    model = _RecordingModel()
    graph = create_agent(
        model,
        tools=[],
        middleware=[_BY_NAME[name] for name in _mounted_pair()],
        checkpointer=InMemorySaver(),
        system_prompt=_IDENTITY,
    )
    config = {"configurable": {"thread_id": "instructions-and-memory"}}
    run_context = {
        "user_instructions": _INSTRUCTIONS,
        "memory_brief_snapshot": {"snapshot_id": "s1", "memory_ctx": {"global_profile": {"name": "Li Ming"}}},
    }

    for question in ("hello", "and again"):
        await graph.ainvoke({"messages": [HumanMessage(content=question)]}, config, context=dict(run_context))

    assert len(model.calls) == 2
    for number, call in enumerate(model.calls, 1):
        assert call[0] == ("SystemMessage", _IDENTITY)
        assert _system_positions(call, _INSTRUCTIONS_TAG) == [1], f"model call {number}: instructions once, first"
        assert 'priority="highest"' in call[1][1], "the header is the only statement that the instructions take precedence"
        assert _system_positions(call, _MEMORY_TAG) == [2], f"model call {number}: memory block once, behind them"
        assert sum(_INSTRUCTIONS in text for _, text in call) == 1
        assert sum("Li Ming" in text for _, text in call) == 1
