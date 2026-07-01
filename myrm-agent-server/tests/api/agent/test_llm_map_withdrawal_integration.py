"""Integration tests: llm_map primitive fully withdrawn from product stack."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from app.services.agent.profile_resolver import ResolvedAgentProfile


@pytest.fixture
def base_request() -> dict:
    return {
        "message_id": "test-msg-llm-map-withdrawal",
        "chat_id": "test-chat-llm-map-withdrawal",
        "query": "hello",
        "model_selection": {
            "providerId": "minimax",
            "model": os.environ.get("BASIC_MODEL", "minimax/MiniMax-M2.7"),
            "baseUrl": os.environ.get("BASIC_BASE_URL", "https://api.minimaxi.com/v1"),
        },
    }


def _resolved_with_legacy_llm_map() -> ResolvedAgentProfile:
    return ResolvedAgentProfile(
        agent_id="legacy-llm-map-agent",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search", "llm_map", "wiki"),
        system_prompt="You are a test agent.",
        model="openai/gpt-4o-mini",
    )


class TestLlmMapWithdrawalTemplatesIntegration:
    def test_templates_exclude_batch_processing_assistant(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/templates")
        assert response.status_code == 200
        templates = response.json()["data"]
        template_ids = {t["id"] for t in templates}
        assert "batch_processing_assistant" not in template_ids

    def test_no_template_references_llm_map_builtin_tool(self, client: TestClient) -> None:
        response = client.get("/api/v1/agents/templates")
        assert response.status_code == 200
        for template in response.json()["data"]:
            tools = template.get("enabled_builtin_tools") or []
            assert "llm_map" not in tools, f"template {template.get('id')} still lists llm_map"


class TestLlmMapWithdrawalConverterIntegration:
    @pytest.mark.asyncio
    async def test_converter_ignores_legacy_llm_map_in_profile_tools(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params
        from app.services.agent.params.models import AgentRequest

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=_resolved_with_legacy_llm_map())

        base_request["agent_id"] = "legacy-llm-map-agent"
        base_request["action_mode"] = "agent"
        request = AgentRequest(**base_request)

        with patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.enable_wiki is True
        assert params.enable_browser is False
        assert not hasattr(params, "enable_llm_map")

    @pytest.mark.asyncio
    async def test_agent_config_legacy_llm_map_does_not_set_enable_llm_map(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params
        from app.services.agent.params.models import AgentRequest

        base_request["action_mode"] = "agent"
        base_request["agent_config"] = {
            "enabledBuiltinTools": ["web_search", "llm_map", "file_ops"],
        }
        request = AgentRequest(**base_request)

        params, _, _, _ = await convert_to_general_agent_params(request, [])

        assert params.enable_file_ops is True
        assert params.enable_browser is False
        assert not hasattr(params, "enable_llm_map")
