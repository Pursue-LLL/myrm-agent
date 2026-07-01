"""Integration tests: llm_map primitive fully withdrawn from product stack."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.services.agent.profile_resolver import ResolvedAgentProfile
from tests.api.agent.utils import get_model_selection


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def base_request() -> dict:
    return {
        "message_id": "test-msg-llm-map-withdrawal",
        "chat_id": "test-chat-llm-map-withdrawal",
        "query": "hello",
        "model_selection": get_model_selection(),
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

    def test_instantiate_batch_processing_template_returns_404(self, client: TestClient) -> None:
        response = client.post("/api/v1/agents/instantiate-template/batch_processing_assistant")
        assert response.status_code == 404


class TestLlmMapWithdrawalProductSurfaceIntegration:
    def test_general_agent_factory_has_no_enable_llm_map_wiring(self) -> None:
        factory_path = (
            Path(__file__).resolve().parents[3]
            / "app"
            / "ai_agents"
            / "general_agent"
            / "factory.py"
        )
        text = factory_path.read_text(encoding="utf-8")
        assert "enable_llm_map" not in text

    def test_general_agent_params_has_no_enable_llm_map_field(self) -> None:
        from app.ai_agents.agents import GeneralAgentParams

        assert "enable_llm_map" not in GeneralAgentParams.model_fields


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


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestLlmMapWithdrawalAgentCrudE2E:
    """DB may retain stale llm_map in enabled_builtin_tools; CRUD must remain usable."""

    async def test_legacy_llm_map_metadata_persists_in_crud(self, async_client: AsyncClient) -> None:
        legacy_tools = ["web_search", "memory", "llm_map", "file_ops"]
        create_payload = {
            "name": "Legacy LlmMap Ghost Agent",
            "description": "E2E: stale llm_map in enabled_builtin_tools",
            "system_prompt": "Reply briefly.",
            "is_built_in": False,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": legacy_tools,
        }

        response = await async_client.post("/api/agents", json=create_payload)
        assert response.status_code == 200
        agent_id = response.json()["data"]["id"]

        try:
            detail_resp = await async_client.get(f"/api/agents/{agent_id}")
            assert detail_resp.status_code == 200
            assert detail_resp.json()["data"]["enabled_builtin_tools"] == legacy_tools
        finally:
            await async_client.delete(f"/api/agents/{agent_id}")
