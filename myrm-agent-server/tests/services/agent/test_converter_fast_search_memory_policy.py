"""A fast turn runs on the default memory policy; the policy saved on an Agent profile never reaches it.

A fast turn is a one-shot answer run, so whichever agent the request names, that agent's saved memory policy does not
apply to it. The general chat turn keeps the policy of its profile.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy
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


@pytest.mark.asyncio
async def test_a_fast_turn_drops_the_memory_policy_saved_on_the_profile() -> None:
    profile = ProfileContext(agent_memory_policy=_SAVED_POLICY)
    request = AgentRequest(message_id="m-fast", chat_id="c-fast", query="Latest Python release?", action_mode="fast")

    surface = await resolve_tool_surface(request, profile, _sources_with_search())

    assert surface.is_fast
    assert profile.agent_memory_policy is None


@pytest.mark.asyncio
async def test_a_general_chat_turn_keeps_the_memory_policy_saved_on_the_profile() -> None:
    profile = ProfileContext(agent_memory_policy=_SAVED_POLICY)
    request = AgentRequest(message_id="m-chat", chat_id="c-chat", query="Latest Python release?", action_mode="agent")

    surface = await resolve_tool_surface(request, profile, _sources_with_search())

    assert not surface.is_fast
    assert profile.agent_memory_policy is _SAVED_POLICY
