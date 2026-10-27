"""A run that uses every round it is given ends on the graph's step limit, with the model's closing answer.

The agent, its middleware chain, the loop guard and the stream executor are real; only the model is scripted.
The model asks for tools in every round and never answers, so each run goes on until something ends it.
What ends it must be the run's own limit event, and every round must be spent: a model that calls three
tools at once uses one round, and the guard must not nudge or stop it as though it had used three. The model
is nudged to wrap up at 70% and 90% of its rounds, in the tool results it reads.
"""

from __future__ import annotations

import itertools
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from pydantic import Field

from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent.types import WorkspaceBinding
from myrm_agent_harness.api import AgentRuntimeSpec
from myrm_agent_harness.core.security.types import SecurityConfig
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

_WARN_NUDGE = "prioritize critical tasks"
_CRITICAL_NUDGE = "Finalize work immediately"


class _NeverAnswers(BaseChatModel):
    """Asks for `calls_per_round` calls of the echo tool in every round, each for a number of its own.

    Notes the round after which each nudge first reached it.
    """

    calls_per_round: int
    asked: Iterator[int] = Field(default_factory=itertools.count)
    nudged_after: dict[str, int] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "never-answers"

    def bind_tools(self, tools: object, **kwargs: object) -> _NeverAnswers:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: object = None, **kwargs: object
    ) -> ChatResult:
        rounds = sum(isinstance(message, AIMessage) for message in messages)
        results = " ".join(str(message.content) for message in messages if isinstance(message, ToolMessage))
        for nudge in (_WARN_NUDGE, _CRITICAL_NUDGE):
            if nudge in results:
                self.nudged_after.setdefault(nudge, rounds)
        calls = [
            {"name": "echo_tool", "args": {"n": n}, "id": f"call_{uuid4().hex}"}
            for n in itertools.islice(self.asked, self.calls_per_round)
        ]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=calls))])


@pytest.mark.parametrize(
    ("max_iterations", "calls_per_round", "warned_after", "told_to_finish_after"), [(5, 1, 3, 4), (10, 3, 7, 9)]
)
@pytest.mark.asyncio
async def test_a_run_that_spends_its_rounds_ends_on_the_limit_event(
    tmp_path: Path, max_iterations: int, calls_per_round: int, warned_after: int, told_to_finish_after: int
) -> None:
    executed = 0

    async def echo(n: int) -> str:
        nonlocal executed
        executed += 1
        return f"echo {n}"

    security = SecurityConfig(yolo_mode_enabled=True, yolo_mode_enabled_at=time.time())
    workspace = (tmp_path / "project").resolve()
    workspace.mkdir()
    binding = WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id="chat_round_budget")
    model = _NeverAnswers(calls_per_round=calls_per_round)
    agent = await create_skill_agent(
        spec=AgentRuntimeSpec(
            agent_id="round-budget",
            name="round-budget",
            system_prompt="You do the task.",
            skill_ids=[],
            workspace_binding=binding,
            max_iterations=max_iterations,
            security_config=security,
        ),
        llm=model,
        tools=[StructuredTool.from_function(coroutine=echo, name="echo_tool", description="Echo a number.")],
        storage_backend=LocalStorageBackend(str(tmp_path / "storage")),
        checkpointer=False,
    )
    context: dict[str, object] = {
        "workspace_path": str(workspace),
        "workspace_binding": binding,
        "workspaces_storage_root": str(tmp_path / "workspaces"),
        "session_id": "chat_round_budget",
    }

    events: Counter[str] = Counter()
    async for event in agent.run(query="do the task", context=context):
        if isinstance(event, dict) and "type" in event:
            events[event["type"]] += 1

    assert events["iteration_limit_reached"] == 1
    assert events["approval_required"] == 0
    assert events["message"] >= 1
    assert executed == max_iterations * calls_per_round
    assert model.nudged_after == {_WARN_NUDGE: warned_after, _CRITICAL_NUDGE: told_to_finish_after}
