"""Swarm fission runs its children through the delegate tool of the agent the business wrapper has built.

Uses a real ``GeneralAgent`` built by the production factory and builder, so the question the harness asks of the agent
it is given (does it carry ``delegate_task_tool``?) is answered by the real object, not by a stand-in.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent import GeneralAgent
from app.ai_agents.general_agent.factory import build_general_agent
from app.core.types.business import ModelConfig
from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.agent.swarm_fission_resume import execute_swarm_fission_for_agent

_CHAT_ID = "fission-chat"
_PAYLOAD: dict[str, object] = {
    "action_type": "swarm_fission",
    "tasks": [{"agent_type": "explore", "objective": "Read the changelog"}],
}
_BATCH: dict[str, object] = {
    "results": [{"task_index": 0, "agent_type": "explore", "success": True, "result": "found"}],
    "total_count": 1,
    "completed_count": 1,
    "failed_count": 0,
}


@pytest.fixture
def checkpointer() -> Iterator[None]:
    set_checkpointer(InMemorySaver())
    yield
    _reset_checkpointer_for_testing()


def _wrapper() -> GeneralAgent:
    params = GeneralAgentParams(
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        query="compare the releases",
        chat_id=_CHAT_ID,
        enable_browser=False,
        prompt_mode="full",
        subagent_ids=["explore"],
    )
    return AgentFactory.create_general_agent(params)


@pytest.mark.asyncio
@pytest.mark.usefixtures("checkpointer")
async def test_children_are_spawned_through_the_delegate_tool_of_the_built_agent() -> None:
    wrapper = _wrapper()
    wrapper.agent = await build_general_agent(wrapper, _CHAT_ID)
    await wrapper.agent._ensure_initialized()

    with patch("myrm_agent_harness.agent.parallel.fission.run_parallel_task_requests", AsyncMock(return_value=_BATCH)) as spawn:
        result = await execute_swarm_fission_for_agent(wrapper, _PAYLOAD)

    assert result["completed_count"] == 1
    assert result["results"] == [
        {"task_index": 0, "agent_type": "explore", "success": True, "result": "found", "error": None, "task_id": None}
    ]
    assert spawn.await_args is not None
    assert spawn.await_args.kwargs["parent_agent"] is wrapper.agent
    assert spawn.await_args.kwargs["delegate_tool"].name == "delegate_task_tool"
    await wrapper.agent.close()


@pytest.mark.asyncio
@pytest.mark.usefixtures("checkpointer")
async def test_a_wrapper_without_a_built_agent_is_refused_instead_of_reported_as_a_failed_batch() -> None:
    wrapper = _wrapper()
    assert wrapper.agent is None

    with pytest.raises(RuntimeError, match="built SkillAgent"):
        await execute_swarm_fission_for_agent(wrapper, _PAYLOAD)
