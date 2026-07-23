"""Tests for execution fingerprint invalidation."""

from __future__ import annotations

from unittest.mock import patch

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import compute_execution_fingerprint


def test_execution_fingerprint_changes_when_skill_version_bumps() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    with patch(
        "app.core.skills.config_version.get_skill_config_version",
        return_value=1.0,
    ):
        first = compute_execution_fingerprint(wrapper)
    with patch(
        "app.core.skills.config_version.get_skill_config_version",
        return_value=2.0,
    ):
        second = compute_execution_fingerprint(wrapper)
    assert first != second


def test_execution_fingerprint_changes_when_security_config_changes() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    wrapper.security_config_raw = {"yoloModeEnabled": True}
    first = compute_execution_fingerprint(wrapper)
    wrapper.security_config_raw = {
        "yoloModeEnabled": False,
        "permissions": {"code_interpreter": "ask"},
    }
    second = compute_execution_fingerprint(wrapper)
    assert first != second
