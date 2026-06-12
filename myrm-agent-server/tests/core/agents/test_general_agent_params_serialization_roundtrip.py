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
