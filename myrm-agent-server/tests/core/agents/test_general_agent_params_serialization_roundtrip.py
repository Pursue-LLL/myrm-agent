"""Offline durable tasks persist `GeneralAgentParams` via model_dump → model_validate."""

from __future__ import annotations

from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

from app.ai_agents import GeneralAgentParams
from app.core.types import ModelConfig


def test_general_agent_params_json_dump_validate_preserves_browser_and_auto_restore() -> None:
    """Same path as `streaming.py` durable registration and `lifecycle/system.py` resume."""
    original = GeneralAgentParams(
        query="task",
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        search_service_cfg=SearchServiceConfig(search_service="tavily"),
        enable_browser=True,
        auto_restore_domains=["oauth.example", "github.com"],
    )
    payload = original.model_dump(mode="json")
    assert payload["enable_browser"] is True
    assert payload["auto_restore_domains"] == ["oauth.example", "github.com"]

    restored = GeneralAgentParams.model_validate(payload)
    assert restored.enable_browser is True
    assert restored.auto_restore_domains == ["oauth.example", "github.com"]


def test_general_agent_params_json_dump_validate_preserves_unattended_mode() -> None:
    original = GeneralAgentParams(
        query="task",
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        unattended_mode=True,
    )
    payload = original.model_dump(mode="json")
    assert payload["unattended_mode"] is True

    restored = GeneralAgentParams.model_validate(payload)
    assert restored.unattended_mode is True


def test_general_agent_params_json_dump_validate_preserves_enable_render_ui() -> None:
    original = GeneralAgentParams(
        query="task",
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        enable_render_ui=True,
    )
    payload = original.model_dump(mode="json")
    assert payload["enable_render_ui"] is True

    restored = GeneralAgentParams.model_validate(payload)
    assert restored.enable_render_ui is True


def test_general_agent_params_json_dump_validate_preserves_video_fallback_chain() -> None:
    video_cfgs = [
        ModelConfig(model="gemini-2.5-flash", api_key="video-key", supports_video=True),
        ModelConfig(model="qwen-vl-max", api_key="vision-key", supports_vision=True),
    ]
    original = GeneralAgentParams(
        query="task",
        model_cfg=ModelConfig(model="gpt-4o", api_key="test-key"),
        video_fallback_model_cfgs=video_cfgs,
    )
    payload = original.model_dump(mode="json")
    assert len(payload["video_fallback_model_cfgs"]) == 2
    assert payload["video_fallback_model_cfgs"][0]["model"] == "gemini-2.5-flash"

    restored = GeneralAgentParams.model_validate(payload)
    assert restored.video_fallback_model_cfgs is not None
    assert restored.video_fallback_model_cfgs[0].model == "gemini-2.5-flash"
