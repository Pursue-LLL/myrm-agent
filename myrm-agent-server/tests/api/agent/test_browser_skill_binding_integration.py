"""Integration: browser-automation skill binds via AgentFactory on full request chain."""

from __future__ import annotations

import pytest

from app.ai_agents.agents import AgentFactory
from app.services.agent.browser_skill_binding import BROWSER_AUTOMATION_SKILL_ID
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-browser-skill",
        "chat_id": "test-chat-browser-skill",
        "query": "Open the expense portal and export last week",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
    }


class TestBrowserSkillBindingIntegration:
    """Web chat request → params → Factory must attach peripheral browser-automation skill."""

    @pytest.mark.asyncio
    async def test_converter_does_not_bind_skill_factory_does(self, base_request: dict[str, object]) -> None:
        base_request["agent_config"] = {
            "enabledBuiltinTools": ["web_search", "browser"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.enable_browser is True
        assert BROWSER_AUTOMATION_SKILL_ID not in params.agent_skill_ids

        agent = AgentFactory.create_general_agent(params)
        assert BROWSER_AUTOMATION_SKILL_ID in agent.skill_ids
        assert agent.skill_configs is not None
        assert agent.skill_configs[BROWSER_AUTOMATION_SKILL_ID]["is_core"] is False

    @pytest.mark.asyncio
    async def test_fast_search_skips_browser_skill_bind(self, base_request: dict[str, object]) -> None:
        base_request["action_mode"] = "fast"
        base_request["agent_config"] = {
            "enabledBuiltinTools": ["web_search", "browser"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        assert params.prompt_mode == "search"

        agent = AgentFactory.create_general_agent(params)
        assert BROWSER_AUTOMATION_SKILL_ID not in agent.skill_ids

    @pytest.mark.asyncio
    async def test_cron_channel_params_bind_via_factory(self, base_request: dict[str, object]) -> None:
        """Cron runner builds params then Factory — skill bind must still apply."""
        base_request["agent_config"] = {
            "enabledBuiltinTools": ["web_search", "browser"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])
        params.channel_name = "cron"
        params.prompt_mode = "full"

        agent = AgentFactory.create_general_agent(params)
        assert BROWSER_AUTOMATION_SKILL_ID in agent.skill_ids
