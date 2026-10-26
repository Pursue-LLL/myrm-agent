"""A run's todo list reaches the run that can update it, and no other run in the same workspace.

``run_workspace`` finds the workspace in the ``Runtime`` a hook receives. Whether a run keeps a todo list there
is decided per agent: only an agent holding ``todo_write`` is shown the list and held to it. The agent runs
below are real ``BaseAgent.run`` calls with the production middleware stack; only the model is scripted, so the
runtime object, the context and the bound tools are the ones production hands the middlewares.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.tools import BaseTool, tool
from langgraph.runtime import Runtime
from pydantic import Field

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoItem, TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import write_todos_sync_to_workspace
from myrm_agent_harness.agent.meta_tools.progress.todo_write_tool import create_todo_write_tool
from myrm_agent_harness.agent.middlewares._run_workspace import run_workspace
from myrm_agent_harness.agent.middlewares._session_context import clear_active_tools_for_tests, set_is_subagent
from myrm_agent_harness.agent.middlewares.completion.completion_guard import reset_completion_guard
from myrm_agent_harness.agent.types import AgentRuntimeConfig, WorkspaceBinding
from myrm_agent_harness.core.security.types import PermissionAction, PermissionRule, SecurityConfig
from myrm_agent_harness.toolkits.code_execution import create_executor
from myrm_agent_harness.toolkits.code_execution.executors.base import reset_executor, set_executor

_PARENT_STEP = "migrate the billing database"
_WRITE_OUT = {"name": "file_write_tool", "args": {"path": "out.txt", "content": "x"}, "id": "call_write"}


@pytest.fixture(autouse=True)
def _no_published_tools() -> Iterator[None]:
    clear_active_tools_for_tests()
    yield
    clear_active_tools_for_tests()


def test_a_run_workspace_is_the_workspace_path_in_its_runtime_context() -> None:
    assert run_workspace(Runtime(context={"workspace_path": "/work/chat_1"})) == "/work/chat_1"


@pytest.mark.parametrize(
    "runtime",
    [
        None,
        Runtime(),
        Runtime(context={}),
        Runtime(context={"workspace_path": ""}),
        {"configurable": {"context": {"workspace_path": "/work/chat_1"}}},
    ],
    ids=["no-runtime", "no-context", "empty-context", "empty-path", "dict-shaped-runtime"],
)
def test_a_runtime_without_a_workspace_path_in_its_context_has_no_workspace(runtime: object) -> None:
    assert run_workspace(runtime) is None


class _RecordingModel(FakeMessagesListChatModel):
    """Scripted model that keeps what each request showed it."""

    requests: list[str] = Field(default_factory=list)

    def bind_tools(self, tools: object, **kwargs: object) -> _RecordingModel:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        self.requests.append("\n".join(str(message.content) for message in messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


class _Workspace:
    """A chat workspace whose todo list holds one unfinished step, and the context a run in it gets."""

    def __init__(self, root: Path) -> None:
        self.path = root / "project"
        self.path.mkdir()
        storage = root / "storage"
        storage.mkdir()
        write_todos_sync_to_workspace(
            str(self.path), TodoStore(goal="Ship the release", todos=[TodoItem(id="p1", content=_PARENT_STEP)])
        )
        session_id = f"chat_run_workspace_{root.name}"
        self.context: dict[str, object] = {
            "workspaces_storage_root": str(storage),
            "session_id": session_id,
            "workspace_binding": WorkspaceBinding(mode="chat", root_path=str(self.path), chat_id=session_id),
            "workspace_path": str(self.path),
        }
        self.executor = create_executor()

    def agent(self, model: _RecordingModel, tools: list[BaseTool]) -> BaseAgent:
        base = SecurityConfig.workspace(allowed_roots=(str(self.path),))
        return BaseAgent(
            llm=model,
            executor=self.executor,
            tools=tools,
            config=AgentRuntimeConfig(
                recursion_limit=300,
                security_config=replace(
                    base, ruleset=(*base.ruleset, PermissionRule("*", "*", PermissionAction.ALLOW))
                ),
            ),
        )


async def _run(agent: BaseAgent, query: str, workspace: _Workspace) -> None:
    reset_completion_guard()
    executor_token = set_executor(workspace.executor)
    try:
        async for _ in agent.run(query, context=dict(workspace.context)):
            pass
    finally:
        reset_executor(executor_token)


def _script(*calls: dict[str, object]) -> _RecordingModel:
    """A model that makes ``calls`` one per turn, then answers "done" for ever after."""
    return _RecordingModel(
        responses=[AIMessage(content="", tool_calls=[call]) for call in calls] + [AIMessage(content="done")] * 6
    )


async def _model_requests_of_a_run(root: Path, *, tools_of: str) -> list[str]:
    """Run a scripted agent that writes a file and finishes, in a workspace whose todo list is unfinished.

    ``tools_of`` is "planner" for an agent that holds ``todo_write`` or "worker" for one that does not.
    """
    workspace = _Workspace(root)
    tools: list[BaseTool] = [create_file_write_tool()]
    if tools_of == "planner":
        tools.append(create_todo_write_tool(workspace_root=str(workspace.path)))
    model = _script(_WRITE_OUT)
    await _run(workspace.agent(model, tools), "write out.txt and finish", workspace)
    return model.requests


async def test_a_run_that_can_update_the_todo_list_sees_it_and_is_held_to_it(tmp_path: Path) -> None:
    requests = await _model_requests_of_a_run(tmp_path, tools_of="planner")

    assert _PARENT_STEP in requests[0]
    assert any("incomplete todos" in request for request in requests[1:])
    assert len(requests) > 2


async def test_a_run_in_the_same_workspace_that_cannot_update_it_never_sees_it_nor_is_held_to_it(
    tmp_path: Path,
) -> None:
    requests = await _model_requests_of_a_run(tmp_path, tools_of="worker")

    assert not any(_PARENT_STEP in request for request in requests)
    assert len(requests) == 2


async def test_a_run_that_delegated_to_a_child_is_still_held_to_its_todo_list(tmp_path: Path) -> None:
    """A child agent run nested in a tool publishes its own tool list where its parent reads it; the parent
    must not lose its todo list because of that, and the child must not be handed the parent's."""
    workspace = _Workspace(tmp_path)
    child_model = _script()
    child = workspace.agent(child_model, [create_file_write_tool()])

    @tool
    async def run_child_tool(task: str) -> str:
        """Run a child agent in this workspace and return when it has finished."""
        set_is_subagent(True)
        try:
            async for _ in child.run(task, context=dict(workspace.context)):
                pass
        finally:
            set_is_subagent(False)
        return "child finished"

    parent_model = _script({"name": "run_child_tool", "args": {"task": "look around"}, "id": "call_child"}, _WRITE_OUT)
    parent = workspace.agent(
        parent_model,
        [create_file_write_tool(), create_todo_write_tool(workspace_root=str(workspace.path)), run_child_tool],
    )

    await _run(parent, "delegate, write out.txt and finish", workspace)

    assert any("incomplete todos" in request for request in parent_model.requests[2:])
    assert not any(_PARENT_STEP in request or "incomplete todos" in request for request in child_model.requests)
