"""Incognito chats must not reach the Wiki: it is resolved off at the single point where chat params are built.

Every Wiki surface in an agent run (tools, long-reply auto-archive, post-compaction archive, Deep Research vaulting)
keys off ``params.enable_wiki``, so the converter is where "incognito leaves no trace" has to hold.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from tests.api.agent.utils import get_model_selection


async def _convert(*, incognito_mode: bool, builtin_tools: tuple[str, ...]) -> bool:
    request = AgentRequest(
        message_id="test-msg-incognito-wiki",
        chat_id="test-chat-incognito-wiki",
        query="Summarize what we know about the Q3 plan",
        model_selection=get_model_selection(),
        action_mode="agent",
        agent_id="builtin-economy",
        incognito_mode=incognito_mode,
    )
    profile = ResolvedAgentProfile(
        agent_id="builtin-economy",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=builtin_tools,
        system_prompt=None,
        auto_restore_domains=(),
        engine_params={},
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=profile)

    from tests.api.agent.conftest import _build_mock_user_configs

    with (
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=resolver),
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=_build_mock_user_configs())),
    ):
        params, *_ = await convert_to_general_agent_params(request, [])
    return params.enable_wiki


@pytest.mark.asyncio
async def test_wiki_stays_on_for_a_normal_chat_with_the_wiki_tool_enabled() -> None:
    assert await _convert(incognito_mode=False, builtin_tools=("web_search", "wiki")) is True


@pytest.mark.asyncio
async def test_wiki_is_off_for_an_incognito_chat_even_when_the_wiki_tool_is_enabled() -> None:
    assert await _convert(incognito_mode=True, builtin_tools=("web_search", "wiki")) is False
