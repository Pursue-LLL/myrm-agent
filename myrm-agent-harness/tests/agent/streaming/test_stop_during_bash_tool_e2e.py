"""Stopping a run while a shell command is in flight, through the real agent chain.

A scripted model issues a real ``bash_code_execute_tool`` call that sleeps, inside a real LangGraph agent driven by
the production ``StreamExecutor`` with the production tool interceptor, on a real ``LocalExecutor`` and a real
persistent shell. Stop only flips the run's cancel token, and that alone must end the command and everything it
started, end the run, and keep the model from being asked again.

The assertions are about outcomes and ordering (the sleeper is gone, the run ended, the model was asked once), never
about how long it took.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.meta_tools.bash.bash_code_execute_tool import create_bash_code_execute_tool
from myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware import tool_interceptor_middleware
from myrm_agent_harness.agent.streaming.stream_compactor import StreamCompactor
from myrm_agent_harness.agent.streaming.stream_executor import STREAM_DONE, StreamContext, StreamExecutor
from myrm_agent_harness.agent.types import AgentRunStatistics
from myrm_agent_harness.toolkits.code_execution.config import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.base import set_executor
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor
from myrm_agent_harness.toolkits.code_execution.workspace.storage_root_bind import (
    bind_workspace_storage_root,
    release_workspace_storage_bind_token,
)
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_SETTLE_S = 30.0
_MARKER = "sleep 4711.41"


class _ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


class _FakeCompactor:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def put(self, event: object) -> None:
        self.events.append(event)

    async def flush(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_run_state() -> Iterator[None]:
    yield
    set_cancel_token(None)
    set_executor(None)
    kill_marked(_MARKER)


@pytest.fixture
async def executor(tmp_path: Path) -> AsyncIterator[LocalExecutor]:
    local = LocalExecutor(ExecutionConfig(), workspace_path=str(tmp_path))
    set_executor(local)
    storage_root = bind_workspace_storage_root(tmp_path)
    yield local
    release_workspace_storage_bind_token(storage_root)
    with contextlib.suppress(Exception):
        await asyncio.wait_for(local.close(), timeout=_SETTLE_S)


class _Run:
    """One scripted agent run executing under the production StreamExecutor."""

    def __init__(self, workspace: Path, command: str, token: CancellationToken) -> None:
        self.token = token
        self.model = _ScriptedModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "bash_code_execute_tool",
                            "args": {"reason": "wait for the build", "command": command},
                            "id": "call_1",
                        }
                    ],
                ),
                AIMessage(content="finished"),
            ]
        )
        agent = create_agent(
            self.model, tools=[create_bash_code_execute_tool()], middleware=[tool_interceptor_middleware]
        )
        self.stats = AgentRunStatistics()
        self.compactor = _FakeCompactor()
        context = {
            "locale": "en",
            "session_id": "e2e-stop-bash",
            "workspace_path": str(workspace),
            "workspaces_storage_root": str(workspace),
        }
        ctx = StreamContext(
            agent=agent,
            agent_input={"messages": [HumanMessage(content="run it")]},
            merged_context=context,
            run_config={"configurable": {"context": context, "thread_id": "e2e-stop-bash"}},
            stats=self.stats,
            message_id="e2e_stop_bash",
            cancel_token=token,
            steering_token=None,
            source_tracker=MagicMock(),
            output_queue=asyncio.Queue(),
        )
        self.executor = StreamExecutor(
            ctx=ctx, fallback_llm=None, safety_fallback_llm=None, rebuild_agent_fn=MagicMock()
        )
        self.executor._compactor = cast(StreamCompactor, self.compactor)

    def start(self) -> asyncio.Task[None]:
        set_cancel_token(self.token)  # as the agent runtime does before it spawns the executor task
        return asyncio.create_task(self.executor.execute())


@pytest.mark.asyncio
async def test_stop_ends_the_command_and_the_run_and_the_model_is_not_asked_again(
    executor: LocalExecutor, tmp_path: Path
) -> None:
    run = _Run(tmp_path, f"echo started && {_MARKER} && echo never", CancellationToken("e2e_stop_bash"))
    executing = run.start()
    await wait_until(lambda: process_alive(_MARKER), _SETTLE_S)

    run.token.cancel(CancelReason.USER_CANCELLED)
    await asyncio.wait_for(executing, timeout=_SETTLE_S)

    assert not process_alive(_MARKER), "the command the stop interrupted must not outlive the run"
    assert run.stats.was_cancelled
    assert run.compactor.events[-1] is STREAM_DONE
    assert run.model.i == 1, "no further model request may follow the stop"


@pytest.mark.asyncio
async def test_a_run_nobody_stops_runs_its_command_to_the_end(executor: LocalExecutor, tmp_path: Path) -> None:
    """Control: the same chain finishes on its own, so the stop above is what ended the first run."""
    run = _Run(tmp_path, "echo started", CancellationToken("e2e_no_stop_bash"))

    await asyncio.wait_for(run.start(), timeout=_SETTLE_S)

    assert not run.stats.was_cancelled
    answers = [event for event in run.compactor.events if getattr(event, "type", None) == "message"]
    assert [getattr(event, "data", None) for event in answers] == ["finished"], (
        "the model saw the command's result and answered"
    )
