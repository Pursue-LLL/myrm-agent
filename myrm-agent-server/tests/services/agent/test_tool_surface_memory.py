"""The entry surface decides which memory policy a turn runs on and how memory reaches the model.

A fast turn is a one-shot answer run: whichever agent the request names, that agent's saved memory policy does not
apply, and no memory tool is mounted (the injected memory block is the only memory surface). The general chat turn
keeps the policy of its profile and gets the memory tools.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy, RecallMode
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.services.agent.params.conversion import ConfigSources, ProfileContext, resolve_tool_surface
from app.services.agent.params.models import AgentRequest

_SAVED_POLICY = AgentMemoryPolicy(write_policy=MemoryWritePolicy.TASK, allow_l3_extraction=False)


def _sources_with_search() -> ConfigSources:
    """Sources whose search service is already resolved, so surface resolution reloads no configuration."""
    return ConfigSources(
        search_cfg=SearchServiceConfig(search_service="tavily", api_key="test-key"),
        search_available=True,
        search_is_user_configured=True,
        embedding_cfg=None,
        reranker_cfg=None,
        mcp_configs=None,
    )


def _request(action_mode: str) -> AgentRequest:
    return AgentRequest(message_id="m-1", chat_id="c-1", query="Latest Python release?", action_mode=action_mode)


@pytest.mark.asyncio
async def test_a_fast_turn_drops_the_memory_policy_saved_on_the_profile() -> None:
    profile = ProfileContext(agent_memory_policy=_SAVED_POLICY)

    surface = await resolve_tool_surface(_request("fast"), profile, _sources_with_search())

    assert surface.is_fast
    assert profile.agent_memory_policy is None


@pytest.mark.asyncio
async def test_a_general_chat_turn_keeps_the_memory_policy_saved_on_the_profile() -> None:
    profile = ProfileContext(agent_memory_policy=_SAVED_POLICY)

    surface = await resolve_tool_surface(_request("agent"), profile, _sources_with_search())

    assert not surface.is_fast
    assert profile.agent_memory_policy is _SAVED_POLICY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action_mode", "recall_mode"),
    [("fast", RecallMode.CONTEXT), ("agent", RecallMode.HYBRID)],
)
async def test_the_surface_decides_whether_memory_tools_are_mounted(action_mode: str, recall_mode: RecallMode) -> None:
    surface = await resolve_tool_surface(_request(action_mode), ProfileContext(), _sources_with_search())

    assert surface.memory_recall_mode is recall_mode
