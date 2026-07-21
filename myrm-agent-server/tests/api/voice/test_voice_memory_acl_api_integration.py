"""API integration: Voice memory ACL over HTTP (ACL path unmocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.api.voice.test_realtime import _providers


def _voice_app(*, include_gemini: bool = False) -> FastAPI:
    from app.api.voice.realtime import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/voice")
    if include_gemini:
        from app.api.voice.gemini_live import router as gemini_router

        app.include_router(gemini_router, prefix="/api/v1/voice")
    return app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_token_http_declares_sessions_corpus_when_settings_on() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {}
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {
        "enableMemory": True,
        "memoryEnableConversationSearch": True,
    }

    mock_profile = MagicMock()
    mock_profile.model = None
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-integration", "expires_at": None}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    app = _voice_app()
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/voice/realtime-token", json={})

    assert response.status_code == 200
    body = response.json()
    memory_tool = next(t for t in body["tools"] if t["name"] == "memory_search_tool")
    corpus_enum = memory_tool["parameters"]["properties"]["corpus"]["enum"]
    assert "sessions" in corpus_enum
    assert "all" in corpus_enum


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_tool_exec_http_passes_conversation_search_acl() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {
        "enableMemory": True,
        "memoryEnableConversationSearch": True,
    }
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params):
        yield {"type": "message", "data": "integration-ok"}

    app = _voice_app()
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=None),
        patch("app.core.channel_bridge.config_parsers.extract_retrieval_models", return_value=(None, None)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        patch("app.api.voice.realtime._ensure_model_rebuild_for_tool_exec", return_value=None),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/realtime-tool-exec",
                json={
                    "tool_name": "memory_search_tool",
                    "arguments": {"query": "budget", "corpus": "sessions"},
                    "agent_id": "builtin-general",
                },
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("error") is None
    assert "integration-ok" in str(payload.get("result"))
    assert captured.get("enable_memory") is True
    assert captured.get("enable_conversation_search") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_tool_exec_http_blocks_sessions_when_opt_in_off() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": True}
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params):
        yield {"type": "message", "data": "ok"}

    app = _voice_app()
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=None),
        patch("app.core.channel_bridge.config_parsers.extract_retrieval_models", return_value=(None, None)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        patch("app.api.voice.realtime._ensure_model_rebuild_for_tool_exec", return_value=None),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/realtime-tool-exec",
                json={
                    "tool_name": "memory_search_tool",
                    "arguments": {"query": "budget", "corpus": "sessions"},
                },
            )

    assert response.status_code == 200
    assert captured.get("enable_conversation_search") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gemini_live_token_http_declares_sessions_corpus_when_settings_on() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = {
        "providers": [
            {
                "id": "google",
                "apiUrl": "https://generativelanguage.googleapis.com/v1",
                "apiKeys": [{"id": "k0", "key": "AIza-integration", "isActive": True, "remark": ""}],
                "enabledModels": [],
            }
        ],
        "defaultModelConfig": {},
    }
    mock_configs.personal_settings_dict = {
        "enableMemory": True,
        "memoryEnableConversationSearch": True,
    }

    mock_profile = MagicMock()
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    app = _voice_app(include_gemini=True)
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/voice/gemini-live-token", json={})

    assert response.status_code == 200
    body = response.json()
    memory_tool = next(t for t in body["tools"] if t["name"] == "memory_search_tool")
    corpus_enum = memory_tool["parameters"]["properties"]["corpus"]["enum"]
    assert "sessions" in corpus_enum
    assert "all" in corpus_enum
