"""Integration: video_fallback_model_cfgs through convert_to_general_agent_params → GeneralAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai_agents.agents import AgentFactory
from app.core.channel_bridge.config_loader import UserConfigs
from app.core.types import ModelConfig
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest

# A slot resolves to the first enabled row carrying its provider id, so the chat provider
# must not reuse the id of the video provider ("openai") whatever the environment's chat model is.
_CHAT_PROVIDER_ID = "chat-provider"
_CHAT_MODEL = "chat-model"


def _providers_with_video_fallback() -> dict[str, object]:
    return {
        "defaultModelConfig": {
            "baseModel": {
                "primary": {"providerId": _CHAT_PROVIDER_ID, "model": _CHAT_MODEL},
            },
            "videoFallbackModel": {
                "primary": {"providerId": "openai", "model": "gpt-4o-mini"},
            },
            "visionFallbackModel": {
                "primary": {"providerId": "openai", "model": "gpt-4o"},
            },
        },
        "providers": [
            {
                "id": _CHAT_PROVIDER_ID,
                "isEnabled": True,
                "providerType": "openai",
                "apiUrl": "https://chat.example.test/v1",
                "apiKeys": [{"key": "sk-chat-test", "isActive": True}],
                "enabledModels": [_CHAT_MODEL],
            },
            {
                "id": "openai",
                "isEnabled": True,
                "providerType": "openai",
                "apiUrl": "https://api.openai.com/v1",
                "apiKeys": [{"key": "sk-video-test", "isActive": True}],
                "enabledModels": ["gpt-4o-mini", "gpt-4o"],
            },
        ],
        "customModelInfo": {
            "openai/gpt-4o-mini": {"supports_video_input": True},
        },
    }


def _mock_user_configs() -> UserConfigs:
    return UserConfigs(
        model_cfg=ModelConfig(model="openai/gpt-4o-mini", api_key="sk-chat"),
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=None,
        personal_settings_dict=None,
        mcp_dict=None,
        providers_dict=_providers_with_video_fallback(),
        security_config_dict={"yoloModeEnabled": False, "autoModeEnabled": False},
    )


@pytest.fixture
def base_request() -> dict[str, object]:
    return {
        "message_id": "test-msg-video-fallback",
        "chat_id": "test-chat-video-fallback",
        "query": "summarize the attached video",
        "model_selection": {"providerId": _CHAT_PROVIDER_ID, "model": _CHAT_MODEL},
        "action_mode": "agent",
        "agent_config": {"enabledBuiltinTools": ["web_search"]},
    }


class TestVideoFallbackConverterIntegration:
    """P0 evidence chain: converter must emit video_fallback_model_cfgs into agent runtime."""

    @pytest.mark.asyncio
    async def test_converter_propagates_video_fallback_to_general_agent_params(self, base_request: dict[str, object]) -> None:
        request = AgentRequest(**base_request)

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=_mock_user_configs()),
        ):
            params, *rest = await convert_to_general_agent_params(request, [])

        assert params.video_fallback_model_cfgs is not None
        assert len(params.video_fallback_model_cfgs) >= 1
        assert params.video_fallback_model_cfgs[0].model == "openai/gpt-4o-mini"
        assert params.video_fallback_model_cfgs[0].supports_video is True

    @pytest.mark.asyncio
    async def test_agent_factory_preserves_video_fallback_on_instance(self, base_request: dict[str, object]) -> None:
        request = AgentRequest(**base_request)

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=_mock_user_configs()),
        ):
            params, *rest = await convert_to_general_agent_params(request, [])

        agent = AgentFactory.create_general_agent(params)
        assert agent.video_fallback_model_cfgs is not None
        assert agent.video_fallback_model_cfgs[0].model == "openai/gpt-4o-mini"

        context = agent._build_runtime_context(
            query="analyze demo.mp4",
            chat_history=[],
            effective_chat_id="test-chat-video-fallback",
        )
        assert context.get("video_fallback_model_cfgs") == agent.video_fallback_model_cfgs
        assert "supports_video" in context
