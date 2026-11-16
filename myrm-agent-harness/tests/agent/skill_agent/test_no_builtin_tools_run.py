"""An agent of a host that switched the built-in tools off keeps the host's action space for as long as it runs.

The registry an agent rebuilds its graph from (``add_tools``, a model failover) holds only the host's tools after
any number of turns, also when the skill library is large enough to mount ``skill_search_tool`` on an agent that
keeps the built-in tools. The tests run real turns over a scripted model and read what the model is bound with.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents import create_agent
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.language_models import FakeListChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import tool
from pydantic import Field

from myrm_agent_harness.agent.skill_agent import SkillAgent, wait_all_background_tasks
from myrm_agent_harness.agent.skills import SkillMetadata
from myrm_agent_harness.agent.types import AgentRuntimeConfig

_CHAT_ID = "chat_no_builtin_tools"
_LONG_DESCRIPTION = "Handles one narrow kind of work that needs its own detailed procedure and checks. " * 4
# Too large to list inline, so an agent that keeps the built-in tools mounts ``skill_search_tool`` for them.
_SKILLS = [
    SkillMetadata(name=f"skill_{index:03d}", description=_LONG_DESCRIPTION, model_invocable=True, available=True)
    for index in range(120)
]


@tool
def host_a_tool(query: str) -> str:
    """Answer from the host's own data."""
    return "a"


@tool
def host_b_tool(query: str) -> str:
    """Answer from the host's other data."""
    return "b"


class _RecordingModel(FakeListChatModel):
    """Scripted model that records the tools each call is bound with and the prompt each call is sent."""

    bound_tool_names: list[tuple[str, ...]] = Field(default_factory=list)
    prompts: list[str] = Field(default_factory=list)

    def bind_tools(self, tools: Sequence[object], **kwargs: object) -> _RecordingModel:
        self.bound_tool_names.append(tuple(sorted(str(getattr(tool, "name", "")) for tool in tools)))
        return self

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> AsyncIterator[ChatGenerationChunk]:
        self.prompts.append("\n".join(str(message.content) for message in messages))
        async for chunk in super()._astream(messages, stop, run_manager, **kwargs):
            yield chunk

    def offered(self) -> list[tuple[str, ...]]:
        """The distinct tool sets the model was bound with, in the order it saw them."""
        return list(dict.fromkeys(self.bound_tool_names))


def _agent(*, no_builtin_tools: bool) -> tuple[SkillAgent, _RecordingModel]:
    backend = AsyncMock()
    backend.list_skills = AsyncMock(return_value=_SKILLS)
    model = _RecordingModel(responses=["ok"])
    agent = SkillAgent(
        llm=model,
        skill_backend=backend,
        tools=[host_a_tool],
        config=AgentRuntimeConfig(no_builtin_tools=no_builtin_tools),
    )
    return agent, model


async def _run_turn(agent: SkillAgent, tmp_path: Path, query: str = "hello") -> list[dict[str, object]]:
    context: dict[str, object] = {
        "workspaces_storage_root": str(tmp_path / "workspaces"),
        "session_id": _CHAT_ID,
        "chat_id": _CHAT_ID,
    }
    events = [event async for event in agent.run(query, context=context)]
    await wait_all_background_tasks()
    return events


@pytest.mark.asyncio
async def test_a_tool_added_after_a_turn_joins_the_hosts_tools_and_nothing_else(tmp_path: Path) -> None:
    agent, model = _agent(no_builtin_tools=True)

    await _run_turn(agent, tmp_path)
    agent.add_tools([host_b_tool])
    await _run_turn(agent, tmp_path)

    assert model.offered() == [("host_a_tool",), ("host_a_tool", "host_b_tool")]


@pytest.mark.asyncio
async def test_a_failover_rebuilds_the_graph_from_the_hosts_tools_only(tmp_path: Path) -> None:
    agent, _ = _agent(no_builtin_tools=True)
    await _run_turn(agent, tmp_path)

    with patch("langchain.agents.create_agent", wraps=create_agent) as build:
        agent._rebuild_agent_with_llm(_RecordingModel(responses=["ok"]))

    assert [tool.name for tool in build.call_args.kwargs["tools"]] == ["host_a_tool"]


@pytest.mark.asyncio
async def test_after_a_turn_the_registry_holds_only_the_hosts_tools(tmp_path: Path) -> None:
    agent, _ = _agent(no_builtin_tools=True)

    await _run_turn(agent, tmp_path)

    registry = agent._tool_registry
    assert registry.tool_names() == {"host_a_tool"}
    assert [snapshot.name for snapshot in registry.snapshot()] == ["host_a_tool"]


@pytest.mark.asyncio
async def test_an_agent_that_keeps_the_built_in_tools_is_offered_them(tmp_path: Path) -> None:
    agent, model = _agent(no_builtin_tools=False)

    await _run_turn(agent, tmp_path)

    assert {"host_a_tool", "skill_select_tool", "skill_search_tool"} <= set(model.bound_tool_names[0])
    assert agent._tool_registry.has_tool("skill_search_tool")
