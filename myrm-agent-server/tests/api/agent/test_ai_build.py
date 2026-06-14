"""Unit tests for POST /user-agents/ai-build SSE endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

API_PREFIX = "/api/v1"


@pytest.fixture()
def app():
    return build_minimal_app("ai_build")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_ai_build_empty_intent(client: AsyncClient):
    resp = await client.post(f"{API_PREFIX}/user-agents/ai-build", json={"intent": ""})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ai_build_no_model_configured(client: AsyncClient):
    """Should return 422 when no LLM provider is configured."""
    with patch("app.api.agents.ai_build.load_user_configs", new_callable=AsyncMock) as mock_cfg:
        mock_cfg.return_value = MagicMock(providers_dict=None)
        with patch("app.api.agents.ai_build.resolve_model_config") as mock_resolve:
            from myrm_agent_harness.agent.config import ConfigIncompleteError

            mock_resolve.side_effect = ConfigIncompleteError(
                    user_friendly_message={"en": "No model"},
                    technical_details="test",
                    resolution_steps=["Configure a model"],
                )
            resp = await client.post(
                f"{API_PREFIX}/user-agents/ai-build", json={"intent": "test agent"}
            )
            assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ai_build_streams_sse(client: AsyncClient):
    """Should return a streaming SSE response with content chunks."""
    mock_configs = MagicMock(providers_dict={"test": {}}, mcp_dict=None)

    async def _fake_stream(*_args, **_kwargs):
        chunk = MagicMock()
        chunk.content = '{"name": "Test Agent", "description": "A test", "system_prompt": "prompt", "skill_ids": [], "mcp_ids": [], "builtin_tools": []}'
        yield chunk

    mock_llm = MagicMock()
    mock_llm.astream = _fake_stream

    with (
        patch("app.api.agents.ai_build.load_user_configs", new_callable=AsyncMock, return_value=mock_configs),
        patch("app.api.agents.ai_build.resolve_model_config") as mock_resolve,
        patch("app.api.agents.ai_build.enrich_model_context_window") as mock_enrich,
        patch("app.api.agents.ai_build.llm_manager.get_llm_from_config", new_callable=AsyncMock, return_value=mock_llm),
        patch("app.api.agents.ai_build.skills_service") as mock_skills,
    ):
        mock_model_cfg = MagicMock()
        mock_model_cfg.api_keys = []
        mock_model_cfg.model_copy.return_value = mock_model_cfg
        mock_resolve.return_value = mock_model_cfg
        mock_enrich.return_value = mock_model_cfg
        mock_skills.list_skills = AsyncMock(return_value=[])

        resp = await client.post(
            f"{API_PREFIX}/user-agents/ai-build", json={"intent": "daily report writer"}
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        body = resp.text
        assert "data:" in body
        assert '"type":"content"' in body.replace(" ", "").replace("'", '"')


@pytest.mark.asyncio
async def test_collect_available_resources():
    """Test _collect_available_resources returns skill and MCP summaries."""
    from app.api.agents.ai_build import _collect_available_resources

    mock_skill = MagicMock()
    mock_skill.id = "web_search"
    mock_skill.name = "Web Search"
    mock_skill.description = "Search the web"
    mock_skill.enabled = True

    mock_configs = MagicMock(mcp_dict=None)

    with (
        patch("app.api.agents.ai_build.skills_service") as mock_svc,
        patch("app.api.agents.ai_build.load_user_configs", new_callable=AsyncMock, return_value=mock_configs),
    ):
        mock_svc.list_skills = AsyncMock(return_value=[mock_skill])
        skills, mcps = await _collect_available_resources()
        assert len(skills) == 1
        assert skills[0]["id"] == "web_search"
        assert len(mcps) == 0
