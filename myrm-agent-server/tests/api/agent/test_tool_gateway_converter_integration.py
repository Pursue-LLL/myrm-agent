"""Integration: sandbox tool gateway merge through convert_to_general_agent_params."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.platform_utils.sandbox.tool_gateway import ResolvedToolGatewayConfig
from app.services.agent.params.models import AgentConfigRequest, AgentRequest
from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from tests.api.agent.utils import get_model_selection


@pytest.fixture
def base_request() -> dict:
    return {
        "message_id": "test-msg-tool-gateway",
        "chat_id": "test-chat-gateway",
        "query": "search the web for EV trends",
        "model_selection": get_model_selection(),
    }


class TestToolGatewayConverterIntegration:
    @pytest.mark.asyncio
    async def test_sandbox_merge_injects_platform_gateway_without_agent_override(
        self,
        base_request: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        platform = ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="sandbox-vk",
        )

        with patch(
            "app.platform_utils.sandbox.tool_gateway.fetch_sandbox_tool_gateway_config",
            return_value=platform,
        ):
            request = AgentRequest(**base_request)
            params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.tool_gateway_config is not None
        assert params.tool_gateway_config["use_gateway"] is True
        assert params.tool_gateway_config["gateway_url"] == "https://cp.example/tool-relay"
        assert params.tool_gateway_config["auth_token"] == "sandbox-vk"

    @pytest.mark.asyncio
    async def test_sandbox_keeps_explicit_agent_gateway_credentials(
        self,
        base_request: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: True)
        platform = ResolvedToolGatewayConfig(
            use_gateway=True,
            gateway_url="https://cp.example/tool-relay",
            auth_token="platform-vk",
        )
        base_request["agent_config"] = AgentConfigRequest(
            enabled_builtin_tools=["web_search"],
            tool_gateway_config=ToolGatewayConfig(
                use_gateway=True,
                gateway_url="https://agent.example/gw",
                auth_token="agent-vk",
            ),
        )

        with patch(
            "app.platform_utils.sandbox.tool_gateway.fetch_sandbox_tool_gateway_config",
            return_value=platform,
        ):
            request = AgentRequest(**base_request)
            params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.tool_gateway_config is not None
        assert params.tool_gateway_config["gateway_url"] == "https://agent.example/gw"
        assert params.tool_gateway_config["auth_token"] == "agent-vk"

    @pytest.mark.asyncio
    async def test_local_mode_does_not_merge_sandbox_gateway(
        self,
        base_request: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        monkeypatch.setattr("app.config.deploy_mode.is_sandbox", lambda: False)

        request = AgentRequest(**base_request)
        params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.tool_gateway_config is None
