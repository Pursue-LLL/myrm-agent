"""Tests for execution fingerprint invalidation."""

from __future__ import annotations

from unittest.mock import patch

from app.ai_agents.general_agent.agent import GeneralAgent
from app.core.types import ModelConfig
from app.services.agent.execution_cache.fingerprint import compute_execution_fingerprint
from app.services.agent.moa_preset_resolver import (
    MOA_PRESET_DEFAULT_ID,
    MOA_PRESET_REVIEW_ID,
    apply_moa_preset_activation,
)


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


def _moa_profile_engine_params() -> dict[str, object]:
    return {
        "moa_overlay": {
            "enabled": True,
            "reference_model_selections": [
                {"providerId": "openai", "model": "gpt-4o-mini"},
            ],
            "fanout": "user_turn",
        },
    }


def test_execution_fingerprint_changes_when_moa_preset_activated() -> None:
    """POOLED cache must rebuild when chat picker toggles MoA preset on/off."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        engine_params=apply_moa_preset_activation(_moa_profile_engine_params(), None),
    )
    inactive_fp = compute_execution_fingerprint(wrapper)
    wrapper.engine_params = apply_moa_preset_activation(
        _moa_profile_engine_params(),
        MOA_PRESET_DEFAULT_ID,
    )
    active_fp = compute_execution_fingerprint(wrapper)
    assert inactive_fp != active_fp


def test_execution_fingerprint_changes_when_moa_preset_strength_changes() -> None:
    """Preset param overrides (review vs default) must bust execution pool fingerprint."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
        engine_params=apply_moa_preset_activation(
            _moa_profile_engine_params(),
            MOA_PRESET_DEFAULT_ID,
        ),
    )
    default_fp = compute_execution_fingerprint(wrapper)
    wrapper.engine_params = apply_moa_preset_activation(
        _moa_profile_engine_params(),
        MOA_PRESET_REVIEW_ID,
    )
    review_fp = compute_execution_fingerprint(wrapper)
    assert default_fp != review_fp
