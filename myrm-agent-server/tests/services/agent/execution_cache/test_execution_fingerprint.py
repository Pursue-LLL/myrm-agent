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
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
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
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
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
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
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
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
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


def test_execution_fingerprint_changes_when_org_model_policy_revision_bumps() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    with patch(
        "app.services.org_model_policy.revision.get_org_model_policy_revision",
        return_value=0,
    ):
        first = compute_execution_fingerprint(wrapper)
    with patch(
        "app.services.org_model_policy.revision.get_org_model_policy_revision",
        return_value=1,
    ):
        second = compute_execution_fingerprint(wrapper)
    assert first != second


def test_execution_fingerprint_changes_when_auto_extraction_toggles() -> None:
    """POOLED cache must rebuild when the user toggles auto memory extraction."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    enabled_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_memory_auto_extraction = False
    disabled_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp != disabled_fp


def test_execution_fingerprint_changes_when_extraction_preset_changes() -> None:
    """POOLED cache must rebuild when the memory extraction preset is reconfigured."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    default_fp = compute_execution_fingerprint(wrapper)
    wrapper.memory_extraction_preset = "work_assistant"
    reconfigured_fp = compute_execution_fingerprint(wrapper)
    assert default_fp != reconfigured_fp


def test_execution_fingerprint_changes_when_code_execution_network_toggles() -> None:
    """Sandbox network policy is solidified into the executor at build time,
    so the user's privacy setting must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.code_execution_allow_network = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_decay_profile_changes() -> None:
    """Memory decay half-life is solidified into the context pipeline middleware,
    so a profile change must rebuild the pooled unit."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    default_fp = compute_execution_fingerprint(wrapper)
    wrapper.memory_decay_profile = "permanent"
    permanent_fp = compute_execution_fingerprint(wrapper)
    assert default_fp != permanent_fp


def test_execution_fingerprint_changes_when_embedding_config_changes() -> None:
    """Embedding backend is solidified into similarity checks and memory retrieval,
    so swapping the embedding model must rebuild the pooled unit."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

    wrapper.embedding_config = EmbeddingConfig(model="embed-a", api_key="k")
    first_fp = compute_execution_fingerprint(wrapper)
    wrapper.embedding_config = EmbeddingConfig(model="embed-b", api_key="k")
    second_fp = compute_execution_fingerprint(wrapper)
    assert first_fp != second_fp


def test_execution_fingerprint_changes_when_notify_targets_change() -> None:
    """Channel notification tools are loaded from notify_targets at build time,
    so target changes must rebuild the pooled unit."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    empty_fp = compute_execution_fingerprint(wrapper)
    wrapper.notify_targets = ({"channel": "feishu", "target": "g-123"},)
    configured_fp = compute_execution_fingerprint(wrapper)
    assert empty_fp != configured_fp


def test_execution_fingerprint_changes_when_kanban_tool_mode_changes() -> None:
    """Kanban tool assembly follows kanban_tool_mode at build time,
    so the tool mode must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    orchestrator_fp = compute_execution_fingerprint(wrapper)
    wrapper.kanban_tool_mode = "minimal"
    minimal_fp = compute_execution_fingerprint(wrapper)
    assert orchestrator_fp != minimal_fp


def test_execution_fingerprint_changes_when_providers_dict_changes() -> None:
    """Provider routing dict is solidified into the SkillAgent assembly,
    so provider configuration changes must rebuild the pooled unit."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    empty_fp = compute_execution_fingerprint(wrapper)
    wrapper.providers_dict = {"openai": {"api_key": "sk-1"}}
    configured_fp = compute_execution_fingerprint(wrapper)
    assert empty_fp != configured_fp


def test_execution_fingerprint_changes_when_jit_subagents_change() -> None:
    """JIT subagent wiring is solidified into delegate tool assembly,
    so ephemeral subagent changes must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.jit_subagents = {"research": {"agent_id": "researcher"}}
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_force_delegate_changes() -> None:
    """Forced delegation target is solidified into sub-agent wiring,
    so a delegate override must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.force_delegate_agent = "researcher"
    delegated_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != delegated_fp


def test_execution_fingerprint_changes_when_reasoning_model_changes() -> None:
    """Reasoning LLM is wired into the harness spec at build time (factory:113-124),
    so a reasoning-model selection change must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.reasoning_model_cfg = ModelConfig(
        model="qwen3-thinking", api_key="k", base_url="http://x"
    )
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_privacy_routing_changes() -> None:
    """Privacy routing wraps the lite LLM at build time (factory:91,137-139),
    so routing rule changes must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.privacy_routing_raw = {
        "local_model": "llama3",
        "s2_strategy": "cloud_after_redact",
    }
    routed_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != routed_fp


def test_execution_fingerprint_changes_when_safety_fallback_model_changes() -> None:
    """Safety fallback LLM is built at build time (llm_factory:117-123),
    so enabling a safety fallback model must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.safety_fallback_model_cfg = ModelConfig(
        model="safety-guard", api_key="k", base_url="http://x"
    )
    guarded_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != guarded_fp


def test_execution_fingerprint_changes_when_light_model_changes() -> None:
    """Light model is solidified into the harness spec (factory:759),
    so the light-model selection must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.light_model_cfg = ModelConfig(
        model="light-model", api_key="k", base_url="http://x"
    )
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_fallback_lite_model_changes() -> None:
    """Lite managed fallback is applied at build time (factory:106-109),
    so the lite fallback model must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.fallback_lite_model_cfg = ModelConfig(
        model="lite-fallback", api_key="k", base_url="http://x"
    )
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_vision_fallback_model_changes() -> None:
    """Vision fallback model is solidified into vision tools (tool_setup:1245-1252),
    so the vision fallback selection must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.vision_fallback_model_cfg = ModelConfig(
        model="vision-fallback", api_key="k", base_url="http://x"
    )
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_vision_fallback_models_change() -> None:
    """Vision fallback model list is solidified into vision tools,
    so the list contents must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.vision_fallback_model_cfgs = [
        ModelConfig(model="vision-a", api_key="k", base_url="http://x")
    ]
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_video_fallback_models_change() -> None:
    """Video fallback model list is solidified into the harness context (agent:420-425),
    so the list contents must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.video_fallback_model_cfgs = [
        ModelConfig(model="video-a", api_key="k", base_url="http://x")
    ]
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_model_internal_params_change() -> None:
    """Model internal params (base_url/max_context_tokens/supports_vision/
    custom_model_def) are solidified into prompt-mode auto-tuning and the harness
    spec (factory:758-760,1159-1160), so they must bust the POOLED cache."""
    from myrm_agent_harness.agent.config.llm import CustomModelDef

    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    base_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        max_context_tokens=16384,
        supports_vision=True,
        custom_model_def=CustomModelDef(model_id="ollama/llama3", context_length=8192),
    )
    tuned_fp = compute_execution_fingerprint(wrapper)
    assert base_fp != tuned_fp


def test_execution_fingerprint_stable_when_api_key_rotates() -> None:
    """Credential rotation must NOT bust the POOLED cache — keys do not change
    build semantics and must never enter the fingerprint hash."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(
            model="test-model", api_key="test-key", base_url="http://test"
        ),
        mcp_config=None,
    )
    before_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model", api_key="rotated-key", base_url="http://test"
    )
    after_fp = compute_execution_fingerprint(wrapper)
    assert before_fp == after_fp
