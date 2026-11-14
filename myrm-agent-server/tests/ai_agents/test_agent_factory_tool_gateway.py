"""The tool gateway an agent profile configures reaches every tool that can route its traffic through it.

``AgentFactory.create_general_agent`` hands the gateway to web search and to the image, video and speech tools the
profile configured, and leaves the tools it did not configure, and every agent without a gateway, as they were.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents.agent_params import GeneralAgentParams, ImageGenerationParams, TTSParams, VideoGenerationParams
from app.ai_agents.agents import AgentFactory
from app.core.types.business import ModelConfig

_GATEWAY: dict[str, object] = {
    "use_gateway": True,
    "gateway_url": "https://gateway.example/tool-relay",
    "auth_token": "virtual-key",
}


def _params(**overrides: object) -> GeneralAgentParams:
    fields: dict[str, object] = {
        "model_cfg": ModelConfig(model="gpt-4o", api_key="test-key"),
        "query": "hello",
        "chat_id": "chat-gateway",
        "enable_memory": False,
        "enable_browser": False,
        "prompt_mode": "full",
        **overrides,
    }
    return GeneralAgentParams(**fields)


def test_the_gateway_reaches_search_and_every_media_tool_the_profile_configured() -> None:
    params = _params(
        tool_gateway_config=_GATEWAY,
        search_service_cfg=SearchServiceConfig(search_service="searxng", api_base="http://127.0.0.1:8080"),
        image_generation=ImageGenerationParams(),
        video_generation=VideoGenerationParams(),
        tts=TTSParams(),
    )

    AgentFactory.create_general_agent(params)

    assert params.search_service_cfg is not None
    assert params.search_service_cfg.gateway_config == ToolGatewayConfig.model_validate(_GATEWAY)
    assert params.image_generation is not None
    assert params.image_generation.gateway_config == _GATEWAY
    assert params.video_generation is not None
    assert params.video_generation.gateway_config == _GATEWAY
    assert params.tts is not None
    assert params.tts.gateway_config == _GATEWAY


_MEDIA_TOOLS = {"image_generation": ImageGenerationParams, "video_generation": VideoGenerationParams, "tts": TTSParams}


@pytest.mark.parametrize("configured", list(_MEDIA_TOOLS))
def test_only_the_media_tool_the_profile_configured_gets_the_gateway(configured: str) -> None:
    params = _params(tool_gateway_config=_GATEWAY, **{configured: _MEDIA_TOOLS[configured]()})

    AgentFactory.create_general_agent(params)

    assert params.search_service_cfg is None
    for name in _MEDIA_TOOLS:
        tool = getattr(params, name)
        if name == configured:
            assert tool is not None
            assert tool.gateway_config == _GATEWAY
        else:
            assert tool is None


def test_an_agent_without_a_gateway_routes_nothing_through_one() -> None:
    params = _params(
        search_service_cfg=SearchServiceConfig(search_service="searxng", api_base="http://127.0.0.1:8080"),
        image_generation=ImageGenerationParams(),
        video_generation=VideoGenerationParams(),
        tts=TTSParams(),
    )

    AgentFactory.create_general_agent(params)

    assert params.search_service_cfg is not None
    assert params.search_service_cfg.gateway_config is None
    assert params.image_generation is not None
    assert params.image_generation.gateway_config is None
    assert params.video_generation is not None
    assert params.video_generation.gateway_config is None
    assert params.tts is not None
    assert params.tts.gateway_config is None
