"""A delegated child never takes over the delegating agent's todo list.

A child runs in the chat of the agent that delegated to it, so the list in that chat is the
delegating agent's own: a child built over a workspace that already holds it must neither mount
``todo_write`` nor be shown the list. The delegation, the child's run through
``SubagentExecutor._run_single_attempt`` and the child's tool assembly are real; only the model is
scripted.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent.hooks.types import HookEvent
from myrm_agent_harness.agent.meta_tools.progress.todo_write_tool import create_todo_write_tool
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.sub_agents.manager import SubagentManager
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
from myrm_agent_harness.agent.types import WorkspaceBinding
from myrm_agent_harness.api import AgentRuntimeSpec
from myrm_agent_harness.core.context_vars import chat_id_var
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

_PARENT_STEP = "parent step: migrate the billing tables"
_CHAT = "chat_1"


class _RecordingModel(FakeMessagesListChatModel):
    """Answers once and records the text of every request it receives."""

    requests: list[str] = Field(default_factory=list)

    def bind_tools(self, tools: object, **kwargs: object) -> _RecordingModel:
        return self

    def _generate(self, messages: list[BaseMessage], *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        self.requests.append("\n".join(str(message.content) for message in messages))
        return super()._generate(messages, *args, **kwargs)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace holding the unfinished todo of the chat the delegating agent runs in."""
    root = (tmp_path / "project").resolve()
    root.mkdir()
    token = chat_id_var.set(_CHAT)
    try:
        create_todo_write_tool(str(root)).invoke(
            {"todos": [{"id": "1", "content": _PARENT_STEP, "status": "in_progress"}], "merge": False}
        )
    finally:
        chat_id_var.reset(token)
    return root


async def _build_agent(workspace: Path, tmp_path: Path, model: _RecordingModel, *, mode: str) -> SkillAgent:
    """An agent built the way the server builds a child: planning off, bound to the shared workspace."""
    return await create_skill_agent(
        spec=AgentRuntimeSpec(
            agent_id="child",
            name="child",
            system_prompt="You are a delegated child.",
            skill_ids=[],
            workspace_binding=WorkspaceBinding(mode=mode, root_path=str(workspace)),
        ),
        llm=model,
        tools=[],
        storage_backend=LocalStorageBackend(str(tmp_path / "storage")),
        checkpointer=False,
    )


def _tool_names(agent: SkillAgent) -> set[str]:
    assert agent._cached_tools is not None
    return {tool.name for tool in agent._cached_tools}


def _run_context(workspace: Path, tmp_path: Path) -> dict[str, object]:
    """The workspace keys a parent hands every child (`spawn_prep._PARENT_CONTEXT_KEYS`)."""
    return {
        "workspace_path": str(workspace),
        "workspace_binding": WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id=_CHAT),
        "workspaces_storage_root": str(tmp_path / "workspaces"),
        "session_id": _CHAT,
    }


async def _run_top_level(agent: SkillAgent, context: dict[str, object]) -> None:
    async for _ in agent.run(query="continue", context=context):
        pass


async def _delegate(child: SkillAgent, context: dict[str, object]) -> None:
    """Run `child` through the real executor path, exactly as `spawn_child` would."""
    parent = MagicMock()
    parent._last_context = dict(context)
    manager = SubagentManager(parent_agent=parent, current_depth=0)
    parent_taint = MagicMock()
    parent_taint.is_tainted = False

    with (
        patch("myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.build_child_agent", return_value=child),
        patch(
            "myrm_agent_harness.agent.sub_agents.executor_attempt_mixin.get_taint_tracker", return_value=parent_taint
        ),
    ):
        result = await manager._executor._run_single_attempt(
            task_id="child_1",
            agent_type="worker",
            task_description="write the token refresh unit tests",
            config=SubagentConfig(system_prompt="You are a delegated child."),
            context=dict(context),
            tool_registry_getter=lambda: [],
            start_time=time.time(),
            parent_tracker=MagicMock(),
            parent_taint=parent_taint,
            parent_agent=parent,
            cancel_flags=manager._cancel_flags,
            children_agents=manager._children_agents,
            fire_hook=AsyncMock(),
            hook_event_cls=HookEvent,
            trace_id="trace-child-todo",
        )
    assert result.success, result.error


def _scripted(responses: Sequence[str] = ("done",)) -> _RecordingModel:
    return _RecordingModel(responses=[AIMessage(content=text) for text in responses])


@pytest.mark.asyncio
async def test_top_level_agent_resumes_the_workspace_todos(workspace: Path, tmp_path: Path) -> None:
    """The control: the same agent, run on its own, does pick the unfinished list up."""
    model = _scripted()
    agent = await _build_agent(workspace, tmp_path, model, mode="chat")

    await _run_top_level(agent, _run_context(workspace, tmp_path))

    assert "todo_write" in _tool_names(agent)
    assert any(_PARENT_STEP in request for request in model.requests)


@pytest.mark.asyncio
async def test_delegated_child_does_not_mount_todo_write_over_the_parents_list(workspace: Path, tmp_path: Path) -> None:
    model = _scripted()
    child = await _build_agent(workspace, tmp_path, model, mode="subagent")

    await _delegate(child, _run_context(workspace, tmp_path))

    assert "todo_write" not in _tool_names(child)
    assert not any(_PARENT_STEP in request for request in model.requests)
