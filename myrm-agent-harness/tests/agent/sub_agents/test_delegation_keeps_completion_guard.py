"""A run that delegates is still held to verifying what it wrote and to finishing its todo list.

The completion guard reads the run's tool-call history from the loop guard. A child agent runs inside the
parent's delegating tool call; if its run reset the parent's loop guard, the parent's unverified write
would be forgotten and the parent could finish without checking it. The todo list is the running chat's
own, found by the chat the run serves, so a child that rebound that chat would hide it the same way. The
guard's own turn state (how often it has sent the run back) is the run's too: a child that wiped it
would give a run that keeps delegating a fresh refusal budget every time.
The runs below are real ``BaseAgent.run`` calls through the real executor attempt; only the models
are scripted.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.agent.meta_tools.progress.todo_write_tool import create_todo_write_tool
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintTracker
from myrm_agent_harness.agent.sub_agents.executor import SubagentExecutor
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
from tests.agent.middlewares.test_run_workspace import (
    _no_published_tools,  # noqa: F401  (autouse fixture of the shared workspace harness)
    _RecordingModel,
    _run,
    _script,
    _Workspace,
)

_WRITE_APP = {"name": "file_write_tool", "args": {"path": "app.py", "content": "print(1)"}, "id": "call_write"}
_DELEGATE = {"name": "run_child_tool", "args": {"task": "look around"}, "id": "call_child"}
_UNVERIFIED = "NO verification"


async def _run_a_parent_that_can_delegate(
    root: Path, parent_model: _RecordingModel, *, plans: bool = False
) -> list[str]:
    """Run ``parent_model`` as an agent that writes files and delegates; return the tasks it delegated.

    With ``plans`` the parent holds ``todo_write``, and the workspace already has an unfinished list for its chat.
    """
    workspace = _Workspace(root)
    delegated: list[str] = []
    child = workspace.agent(_script(), [create_file_write_tool()])
    parent_agent = MagicMock()
    parent_agent._subagent_manager = None
    parent_agent._last_context = {}

    @tool
    async def run_child_tool(task: str) -> str:
        """Run a child agent in this workspace through the executor and return its answer."""
        delegated.append(task)
        result = await SubagentExecutor()._run_single_attempt(
            task_id=f"task_child_{len(delegated)}",
            agent_type="worker",
            task_description=task,
            config=SubagentConfig(system_prompt="child", timeout_seconds=60),
            context=dict(workspace.context),
            tool_registry_getter=lambda: [],
            start_time=0.0,
            parent_tracker=None,
            parent_taint=TaintTracker(),
            parent_agent=parent_agent,
            cancel_flags={},
            children_agents={},
            fire_hook=AsyncMock(),
            hook_event_cls=MagicMock(),
        )
        return str(result.result)

    tools = [create_file_write_tool(), run_child_tool]
    if plans:
        tools.append(create_todo_write_tool(workspace_root=str(workspace.path)))
    parent = workspace.agent(parent_model, tools)

    with patch(
        "myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.build_child_agent",
        AsyncMock(return_value=child),
    ):
        await _run(parent, "write app.py, look around and finish", workspace)

    return delegated


async def _requests_of_a_run_that_writes_code(root: Path, *, delegates: bool, plans: bool = False) -> list[str]:
    """Run a parent that writes ``app.py`` (never verified), optionally delegates, and finishes."""
    parent_model = _script(_WRITE_APP, _DELEGATE) if delegates else _script(_WRITE_APP)
    await _run_a_parent_that_can_delegate(root, parent_model, plans=plans)
    return parent_model.requests


def _a_parent_that_delegates_each_time_it_is_sent_back(rounds: int) -> _RecordingModel:
    """Writes ``app.py``, then answers "done" and delegates a fresh task whenever the guard refuses to let it end."""
    responses = [AIMessage(content="", tool_calls=[_WRITE_APP])]
    for round_number in range(rounds):
        task = {**_DELEGATE, "args": {"task": f"look around {round_number}"}, "id": f"call_child_{round_number}"}
        responses += [AIMessage(content="done"), AIMessage(content="", tool_calls=[task])]
    return _RecordingModel(responses=[*responses, AIMessage(content="done")])


@pytest.mark.parametrize("delegates", [False, True], ids=["alone", "after-delegating"])
async def test_a_run_is_held_to_verifying_its_code_whether_or_not_it_delegated(tmp_path: Path, delegates: bool) -> None:
    requests = await _requests_of_a_run_that_writes_code(tmp_path, delegates=delegates)

    assert any(_UNVERIFIED in request for request in requests[1:])


@pytest.mark.parametrize("delegates", [False, True], ids=["alone", "after-delegating"])
async def test_a_run_is_held_to_its_todo_list_whether_or_not_it_delegated(tmp_path: Path, delegates: bool) -> None:
    requests = await _requests_of_a_run_that_writes_code(tmp_path, delegates=delegates, plans=True)

    assert any("incomplete todos" in request for request in requests[1:])


async def test_a_run_that_delegates_after_every_refusal_still_runs_out_of_refusals(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    parent_model = _a_parent_that_delegates_each_time_it_is_sent_back(rounds=8)

    with caplog.at_level(logging.WARNING):
        await _run_a_parent_that_can_delegate(tmp_path, parent_model)

    logged = [record.getMessage() for record in caplog.records]
    assert sum("Blocking completion" in message for message in logged) == 3
    assert any("Max rejections (3) reached" in message for message in logged)
    assert not any("Iteration limit reached" in message for message in logged)
