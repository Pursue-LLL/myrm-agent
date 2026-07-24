"""Integration: tool_mount.resolve_agent_mount through convert_to_general_agent_params."""

from __future__ import annotations

import pytest

from app.ai_agents.agents import AgentFactory
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-tool-mount",
        "chat_id": "test-chat-tool-mount",
        "query": "List files in Downloads",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
    }


class TestToolMountConverterIntegration:
    """Web chat request → converter → GeneralAgentParams must apply mount SSOT."""

    @pytest.mark.asyncio
    async def test_general_chat_enables_file_and_shell_meta_tools(
        self, base_request: dict[str, object]
    ) -> None:
        base_request["agent_config"] = {"enabledBuiltinTools": ["web_search"]}
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.enable_file_ops is True
        assert params.enable_shell_tools is True
        assert params.prompt_mode == "full"

        agent = AgentFactory.create_general_agent(params)
        assert agent.enable_file_ops is True
        assert agent.enable_shell_tools is True

    @pytest.mark.asyncio
    async def test_fast_search_disables_file_and_shell_meta_tools(
        self, base_request: dict[str, object]
    ) -> None:
        base_request["action_mode"] = "fast"
        base_request["agent_config"] = {
            "enabledBuiltinTools": ["web_search", "browser"]
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.enable_file_ops is False
        assert params.enable_shell_tools is False
        assert params.enable_evicted_read is True
        assert params.prompt_mode == "search"

        agent = AgentFactory.create_general_agent(params)
        assert agent.enable_file_ops is False
        assert agent.enable_shell_tools is False
        assert agent.enable_evicted_read is True
