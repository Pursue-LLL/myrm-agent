"""A run that uses every round it is given ends on the graph's step limit, with the model's closing answer.

The agent, its middleware chain, the loop guard and the stream executor are real; only the model is scripted.
The model asks for tools in every round and never answers, so each run goes on until something ends it.
What ends it must be the run's own limit event, and every round must be spent: a model that calls three
tools at once uses one round, and the guard must not nudge or stop it as though it had used three. The model
is nudged to wrap up at 70% and 90% of its rounds, in the tool results it reads. Runs of different sessions
that overlap each keep their own rounds, so one run's rounds never bring another run's nudges forward.
"""

from __future__ import annotations

import asyncio
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


class _Session:
    """A real agent for one chat session, with the scripted model that never answers and an echo counter."""

    def __init__(self, tmp_path: Path, session_id: str, max_iterations: int, calls_per_round: int) -> None:
        self.session_id = session_id
        self.max_iterations = max_iterations
        self.executed = 0
        self.model = _NeverAnswers(calls_per_round=calls_per_round)
        self._tmp_path = tmp_path
        self._workspace = (tmp_path / session_id).resolve()
        self._workspace.mkdir()
        self._binding = WorkspaceBinding(mode="chat", root_path=str(self._workspace), chat_id=session_id)

    async def _echo(self, n: int) -> str:
        self.executed += 1
        return f"echo {n}"

    async def run(self) -> Counter[str]:
        """Run the agent until the graph's step limit ends it and count the events it emitted."""
        security = SecurityConfig(yolo_mode_enabled=True, yolo_mode_enabled_at=time.time())
        agent = await create_skill_agent(
            spec=AgentRuntimeSpec(
                agent_id=self.session_id,
                name=self.session_id,
                system_prompt="You do the task.",
                skill_ids=[],
                workspace_binding=self._binding,
                max_iterations=self.max_iterations,
                security_config=security,
            ),
            llm=self.model,
            tools=[StructuredTool.from_function(coroutine=self._echo, name="echo_tool", description="Echo a number.")],
            storage_backend=LocalStorageBackend(str(self._tmp_path / f"storage_{self.session_id}")),
            checkpointer=False,
        )
        context: dict[str, object] = {
            "workspace_path": str(self._workspace),
            "workspace_binding": self._binding,
            "workspaces_storage_root": str(self._tmp_path / "workspaces"),
            "session_id": self.session_id,
        }
        events: Counter[str] = Counter()
        async for event in agent.run(query="do the task", context=context):
            if isinstance(event, dict) and "type" in event:
                events[event["type"]] += 1
        return events


@pytest.mark.parametrize(
    ("max_iterations", "calls_per_round", "warned_after", "told_to_finish_after"), [(5, 1, 3, 4), (10, 3, 7, 9)]
)
@pytest.mark.asyncio
async def test_a_run_that_spends_its_rounds_ends_on_the_limit_event(
    tmp_path: Path, max_iterations: int, calls_per_round: int, warned_after: int, told_to_finish_after: int
) -> None:
    session = _Session(tmp_path, "chat_round_budget", max_iterations, calls_per_round)

    events = await session.run()

    assert events["iteration_limit_reached"] == 1
    assert events["approval_required"] == 0
    assert events["message"] >= 1
    assert session.executed == max_iterations * calls_per_round
    assert session.model.nudged_after == {_WARN_NUDGE: warned_after, _CRITICAL_NUDGE: told_to_finish_after}


@pytest.mark.asyncio
async def test_overlapping_runs_of_different_sessions_keep_their_own_rounds(tmp_path: Path) -> None:
    """A chat and a background job run in one process: each is nudged after its own 7th and 9th round."""
    sessions = [_Session(tmp_path, f"chat_overlap_{name}", max_iterations=10, calls_per_round=1) for name in "ab"]

    all_events = await asyncio.gather(*(session.run() for session in sessions))

    for session, events in zip(sessions, all_events, strict=True):
        assert events["iteration_limit_reached"] == 1
        assert session.executed == 10
        assert session.model.nudged_after == {_WARN_NUDGE: 7, _CRITICAL_NUDGE: 9}
