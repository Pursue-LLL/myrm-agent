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


def test_execution_fingerprint_changes_when_org_model_policy_revision_bumps() -> None:
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    enabled_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_memory_auto_extraction = False
    disabled_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp != disabled_fp


def test_execution_fingerprint_changes_when_extraction_preset_changes() -> None:
    """POOLED cache must rebuild when the memory extraction preset is reconfigured."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    orchestrator_fp = compute_execution_fingerprint(wrapper)
    wrapper.kanban_tool_mode = "minimal"
    minimal_fp = compute_execution_fingerprint(wrapper)
    assert orchestrator_fp != minimal_fp


def test_execution_fingerprint_changes_when_providers_dict_changes() -> None:
    """Provider routing dict is solidified into the SkillAgent assembly, so provider
    model definitions must bust the POOLED cache while credential rotation must not."""
    wrapper = _base_wrapper()
    empty_fp = compute_execution_fingerprint(wrapper)
    wrapper.providers_dict = {
        "providers": [
            {
                "id": "openai",
                "models": [{"id": "gpt-4o", "isActive": True}],
            }
        ],
        "defaultModelConfig": {
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-1",
        },
    }
    configured_fp = compute_execution_fingerprint(wrapper)
    assert empty_fp != configured_fp
    wrapper.providers_dict = {
        "providers": [
            {
                "id": "openai",
                "models": [{"id": "gpt-4o", "isActive": True}],
                "apiKeys": [{"key": "sk-rotated", "isActive": True}],
                "_oauthToken": "tok-2",
            }
        ],
        "defaultModelConfig": {
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-rotated",
        },
    }
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp == rotated_fp
    wrapper.providers_dict = {
        "providers": [
            {
                "id": "openai",
                "models": [{"id": "gpt-4o-mini", "isActive": True}],
            }
        ],
        "defaultModelConfig": {
            "model": "gpt-4o-mini",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-1",
        },
    }
    changed_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp != changed_fp


def test_execution_fingerprint_changes_when_jit_subagents_change() -> None:
    """JIT subagent wiring is solidified into delegate tool assembly,
    so ephemeral subagent changes must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.force_external_agent = "researcher"
    delegated_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != delegated_fp


def test_execution_fingerprint_changes_when_reasoning_model_changes() -> None:
    """Reasoning LLM is wired into the harness spec at build time (factory:113-124),
    so a reasoning-model selection change must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.reasoning_model_cfg = ModelConfig(model="qwen3-thinking", api_key="k", base_url="http://x")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_privacy_routing_changes() -> None:
    """Privacy routing wraps the lite LLM at build time (factory:91,137-139),
    so routing rule changes must bust the POOLED cache while localApiKey rotation
    (build_privacy_routing_config local LLM credential) must not."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.privacy_routing_raw = {
        "localModel": "llama3",
        "localBaseUrl": "http://localhost:11434",
        "localApiKey": "ollama-key-1",
        "s2Strategy": "cloud_after_redact",
    }
    routed_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != routed_fp
    wrapper.privacy_routing_raw = {
        "localModel": "llama3",
        "localBaseUrl": "http://localhost:11434",
        "localApiKey": "ollama-key-rotated",
        "s2Strategy": "cloud_after_redact",
    }
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert routed_fp == rotated_fp
    wrapper.privacy_routing_raw = {
        "localModel": "qwen3-local",
        "localBaseUrl": "http://localhost:11434",
        "localApiKey": "ollama-key-1",
        "s2Strategy": "cloud_after_redact",
    }
    changed_fp = compute_execution_fingerprint(wrapper)
    assert routed_fp != changed_fp


def test_execution_fingerprint_changes_when_safety_fallback_model_changes() -> None:
    """Safety fallback LLM is built at build time (llm_factory:117-123),
    so enabling a safety fallback model must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.safety_fallback_model_cfg = ModelConfig(model="safety-guard", api_key="k", base_url="http://x")
    guarded_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != guarded_fp


def test_execution_fingerprint_changes_when_light_model_changes() -> None:
    """Light model is solidified into the harness spec (factory:759),
    so the light-model selection must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.light_model_cfg = ModelConfig(model="light-model", api_key="k", base_url="http://x")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_fallback_lite_model_changes() -> None:
    """Lite managed fallback is applied at build time (factory:106-109),
    so the lite fallback model must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.fallback_lite_model_cfg = ModelConfig(model="lite-fallback", api_key="k", base_url="http://x")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_vision_fallback_model_changes() -> None:
    """Vision fallback model is solidified into vision tools (tool_setup:1245-1252),
    so the vision fallback selection must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.vision_fallback_model_cfg = ModelConfig(model="vision-fallback", api_key="k", base_url="http://x")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_vision_fallback_models_change() -> None:
    """Vision fallback model list is solidified into vision tools,
    so the list contents must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.vision_fallback_model_cfgs = [ModelConfig(model="vision-a", api_key="k", base_url="http://x")]
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_video_fallback_models_change() -> None:
    """Video fallback model list is solidified into the harness context (agent:420-425),
    so the list contents must bust the POOLED cache."""
    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.video_fallback_model_cfgs = [ModelConfig(model="video-a", api_key="k", base_url="http://x")]
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_model_internal_params_change() -> None:
    """Model internal params (base_url/max_context_tokens/supports_vision/
    custom_model_def) are solidified into prompt-mode auto-tuning and the harness
    spec (factory:758-760,1159-1160), so they must bust the POOLED cache."""
    from myrm_agent_harness.agent.config.llm import CustomModelDef

    wrapper = GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
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
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )
    before_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(model="test-model", api_key="rotated-key", base_url="http://test")
    after_fp = compute_execution_fingerprint(wrapper)
    assert before_fp == after_fp


def _base_wrapper() -> GeneralAgent:
    """Minimal wrapper with a stable model for fingerprint diffing."""
    return GeneralAgent(
        model_cfg=ModelConfig(model="test-model", api_key="test-key", base_url="http://test"),
        mcp_config=None,
    )


def test_execution_fingerprint_changes_when_conversation_search_toggles() -> None:
    """conversation_history tool group is derived at build time (active_tool_groups:83-88),
    so toggling history search must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_conversation_search = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_advanced_retrieval_toggles() -> None:
    """Advanced retrieval mounts embedding/reranker into web_fetch at build time
    (tool_setup:292-294), so the retrieval switch must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_advanced_retrieval = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_reranker_config_changes() -> None:
    """Reranker backend is solidified into web_fetch (tool_setup:325), so swapping
    the reranker model must bust the POOLED cache while api_key rotation must not."""
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.reranker_config = RerankerConfig(model="cohere/rerank-v3.5", api_key="k")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp
    wrapper.reranker_config = RerankerConfig(model="cohere/rerank-v3.5", api_key="rotated")
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp == rotated_fp


def test_execution_fingerprint_changes_when_skill_market_toggles() -> None:
    """Skill market tool is mounted at build time (factory:772-775),
    so toggling the tool must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_skill_market = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_skill_manage_toggles() -> None:
    """Skill management tool is mounted at build time (factory:772-775),
    so toggling the tool must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.enable_skill_manage = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_memory_confirmation_toggles() -> None:
    """Memory write approval is solidified into the memory tool (tool_setup:902),
    so the confirmation switch must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.memory_require_confirmation = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_memory_policy_changes() -> None:
    """Memory isolation policy is resolved into context binding at build time
    (agent:362 → factory:674,704), so policy changes must bust the POOLED cache."""
    from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

    wrapper = _base_wrapper()
    inherit_fp = compute_execution_fingerprint(wrapper)
    wrapper.memory_policy = AgentMemoryPolicy(conversation_id="conv-1")
    scoped_fp = compute_execution_fingerprint(wrapper)
    assert inherit_fp != scoped_fp


def test_execution_fingerprint_changes_when_kanban_default_board_changes() -> None:
    """Kanban default board resolves the dispatcher at build time (factory:1057-1063),
    so the board override must bust the POOLED cache."""
    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.kanban_default_board_id = "board-1"
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp


def test_execution_fingerprint_changes_when_fetch_raw_toggles() -> None:
    """Web fetch raw-markdown mode is solidified at build time (tool_setup:327),
    so the toggle must bust the POOLED cache."""
    wrapper = _base_wrapper()
    off_fp = compute_execution_fingerprint(wrapper)
    wrapper.fetch_raw_webpage = True
    on_fp = compute_execution_fingerprint(wrapper)
    assert off_fp != on_fp


def test_execution_fingerprint_changes_when_auto_restore_domains_change() -> None:
    """Browser auto-restore domains are solidified into the session at build time
    (tool_setup:1100), so list changes must bust the POOLED cache."""
    wrapper = _base_wrapper()
    empty_fp = compute_execution_fingerprint(wrapper)
    wrapper.auto_restore_domains = ["example.com"]
    configured_fp = compute_execution_fingerprint(wrapper)
    assert empty_fp != configured_fp


def test_execution_fingerprint_changes_when_search_service_cfg_changes() -> None:
    """Search service backend is mounted at build time (tool_setup:342-345), so engine
    or base_url changes must bust the POOLED cache while api_key rotation must not."""
    from myrm_agent_harness.toolkits.web_search.providers.web_searcher import SearchServiceConfig

    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.search_service_cfg = SearchServiceConfig(search_service="searxng", api_key="k", api_base="http://searx")
    configured_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != configured_fp
    wrapper.search_service_cfg = SearchServiceConfig(search_service="searxng", api_key="rotated", api_base="http://searx")
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp == rotated_fp
    wrapper.search_service_cfg = SearchServiceConfig(search_service="tavily", api_key="k", api_base="http://tavily")
    swapped_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp != swapped_fp


def test_execution_fingerprint_changes_when_image_generation_params_change() -> None:
    """Image generation tool is mounted only when params are present (tool_setup:547,
    active_tool_groups:96), so enabling or reconfiguring must bust the POOLED cache
    while api_key rotation must not."""
    from app.ai_agents.agents import ImageGenerationParams

    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key="k")
    enabled_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != enabled_fp
    wrapper.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key="rotated")
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp == rotated_fp
    wrapper.image_generation_params = ImageGenerationParams(model="gpt-image-1", api_key="k")
    changed_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp != changed_fp


def test_execution_fingerprint_changes_when_video_generation_params_change() -> None:
    """Video generation tool is mounted only when params are present (tool_setup:618,
    active_tool_groups:97), so enabling or reconfiguring must bust the POOLED cache."""
    from app.ai_agents.agents import VideoGenerationParams

    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.video_generation_params = VideoGenerationParams(provider="openai", model="sora", api_key="k")
    enabled_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != enabled_fp
    wrapper.video_generation_params = VideoGenerationParams(provider="openai", model="veo-3", api_key="k")
    changed_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp != changed_fp


def test_execution_fingerprint_changes_when_tts_params_change() -> None:
    """TTS tool is mounted only when params are present (active_tool_groups:98),
    so enabling or reconfiguring must bust the POOLED cache."""
    from app.ai_agents.agents import TTSParams

    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.tts_params = TTSParams(provider="openai", model="tts-1", voice="alloy", api_key="k")
    enabled_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != enabled_fp
    wrapper.tts_params = TTSParams(provider="openai", model="tts-1", voice="onyx", api_key="k")
    changed_fp = compute_execution_fingerprint(wrapper)
    assert enabled_fp != changed_fp


def test_execution_fingerprint_stable_when_embedding_api_key_rotates() -> None:
    """Embedding credentials are stripped before hashing, so api_key rotation must not
    bust the POOLED cache while model changes still must."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

    wrapper = _base_wrapper()
    wrapper.embedding_config = EmbeddingConfig(model="embed-a", api_key="k")
    first_fp = compute_execution_fingerprint(wrapper)
    wrapper.embedding_config = EmbeddingConfig(model="embed-a", api_key="rotated")
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert first_fp == rotated_fp
    wrapper.embedding_config = EmbeddingConfig(model="embed-b", api_key="k")
    changed_fp = compute_execution_fingerprint(wrapper)
    assert first_fp != changed_fp


def test_execution_fingerprint_stable_when_openapi_credentials_rotate() -> None:
    """OpenAPI bridge AuthConfig carries api_key/bearer_token/password/client_secret
    (harness config.py:58-69), which must be stripped before hashing — credential
    rotation must not bust the POOLED cache while spec/endpoint changes must."""
    wrapper = _base_wrapper()
    wrapper.openapi_services = [
        {
            "name": "stripe",
            "spec_url": "https://api.stripe.com/openapi.json",
            "base_url": "https://api.stripe.com",
            "auth": {
                "type": "api_key",
                "api_key": "sk-live-1",
                "api_key_header": "Authorization",
            },
            "selected_endpoints": ["list_charges"],
        }
    ]
    first_fp = compute_execution_fingerprint(wrapper)
    wrapper.openapi_services = [
        {
            "name": "stripe",
            "spec_url": "https://api.stripe.com/openapi.json",
            "base_url": "https://api.stripe.com",
            "auth": {
                "type": "api_key",
                "api_key": "sk-live-rotated",
                "api_key_header": "Authorization",
            },
            "selected_endpoints": ["list_charges"],
        }
    ]
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert first_fp == rotated_fp
    wrapper.openapi_services = [
        {
            "name": "stripe",
            "spec_url": "https://api.stripe.com/openapi.json",
            "base_url": "https://api.stripe.com",
            "auth": {
                "type": "bearer",
                "bearer_token": "tok-rotated",
                "password": "pw",
                "client_secret": "sec",
            },
            "selected_endpoints": ["list_charges"],
        }
    ]
    auth_swapped_fp = compute_execution_fingerprint(wrapper)
    assert first_fp == auth_swapped_fp
    wrapper.openapi_services = [
        {
            "name": "stripe",
            "spec_url": "https://api.stripe.com/openapi.json",
            "base_url": "https://api.stripe.com",
            "auth": {"type": "api_key", "api_key": "sk-live-1"},
            "selected_endpoints": ["retrieve_charge"],
        }
    ]
    endpoint_fp = compute_execution_fingerprint(wrapper)
    assert first_fp != endpoint_fp


def test_execution_fingerprint_stable_when_external_agent_credentials_rotate() -> None:
    """External ACP agent configs (name/command/args/authMode) are build-solidified
    (external_agents_runtime_config:104-129); any embedded api_key must be stripped
    before hashing so credential rotation does not bust the POOLED cache while a
    command/args change still must."""
    wrapper = _base_wrapper()
    wrapper.external_agents_config = [
        {
            "name": "codex",
            "type": "cli",
            "command": "codex",
            "args": ["exec"],
            "authMode": "api_key",
            "api_key": "sk-1",
        }
    ]
    first_fp = compute_execution_fingerprint(wrapper)
    wrapper.external_agents_config = [
        {
            "name": "codex",
            "type": "cli",
            "command": "codex",
            "args": ["exec"],
            "authMode": "api_key",
            "api_key": "sk-rotated",
        }
    ]
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert first_fp == rotated_fp
    wrapper.external_agents_config = [
        {
            "name": "codex",
            "type": "cli",
            "command": "codex",
            "args": ["exec", "--json"],
            "authMode": "api_key",
            "api_key": "sk-1",
        }
    ]
    changed_fp = compute_execution_fingerprint(wrapper)
    assert first_fp != changed_fp


def test_execution_fingerprint_changes_when_model_kwargs_change() -> None:
    """model_kwargs (temperature/max_tokens/reasoning_effort) are frozen into the
    LLM instance at build time (builder.py:125-135, manager.py:238), so changing
    them must bust the POOLED cache."""
    wrapper = _base_wrapper()
    base_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        model_kwargs={"temperature": 0.7, "max_tokens": 2048},
    )
    configured_fp = compute_execution_fingerprint(wrapper)
    assert base_fp != configured_fp
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        model_kwargs={"temperature": 1.0, "max_tokens": 2048},
    )
    changed_fp = compute_execution_fingerprint(wrapper)
    assert configured_fp != changed_fp


def test_execution_fingerprint_changes_when_temperature_field_changes() -> None:
    """The top-level temperature field is frozen into the LLM instance at build
    time (builder.py:132-133), so a change must bust the POOLED cache."""
    wrapper = _base_wrapper()
    none_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        temperature=0.2,
    )
    chilled_fp = compute_execution_fingerprint(wrapper)
    assert none_fp != chilled_fp
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        temperature=0.8,
    )
    heated_fp = compute_execution_fingerprint(wrapper)
    assert chilled_fp != heated_fp


def test_execution_fingerprint_stable_when_model_kwargs_credentials_rotate() -> None:
    """model_kwargs may carry runtime-only values: credentials (api_key variants)
    and transport headers injected at resolve time (extra_headers with
    X-Sandbox-Id/X-Telemetry-Token/Authorization). Their rotation must NOT bust
    the POOLED cache while non-credential kwargs changes still must."""
    wrapper = _base_wrapper()
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        model_kwargs={
            "temperature": 0.7,
            "extra_headers": {
                "X-Sandbox-Id": "sandbox-1",
                "X-Telemetry-Token": "tok-1",
            },
        },
    )
    first_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        model_kwargs={
            "temperature": 0.7,
            "extra_headers": {
                "X-Sandbox-Id": "sandbox-2",
                "X-Telemetry-Token": "tok-rotated",
            },
        },
    )
    rotated_fp = compute_execution_fingerprint(wrapper)
    assert first_fp == rotated_fp
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="test-key",
        base_url="http://test",
        model_kwargs={"temperature": 0.9},
    )
    changed_fp = compute_execution_fingerprint(wrapper)
    assert first_fp != changed_fp


def test_execution_fingerprint_changes_when_credential_pool_strategy_changes() -> None:
    """credential_pool_strategy is frozen into CredentialPool at build time
    (manager.py:192, credential_pool.py:142-144) and drives acquire() dispatch
    every call (key_pool_llm.py:100), so changing it must bust the POOLED cache
    — in both the ModelConfig field and the providers_dict camelCase key."""
    wrapper = _base_wrapper()
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="k-1",
        api_keys=["k-1", "k-2"],
        credential_pool_strategy="round_robin",
        base_url="http://test",
    )
    round_robin_fp = compute_execution_fingerprint(wrapper)
    wrapper.model_cfg = ModelConfig(
        model="test-model",
        api_key="k-1",
        api_keys=["k-1", "k-2"],
        credential_pool_strategy="least_used",
        base_url="http://test",
    )
    least_used_fp = compute_execution_fingerprint(wrapper)
    assert round_robin_fp != least_used_fp

    wrapper.providers_dict = {
        "providers": [
            {
                "id": "openai",
                "models": [{"id": "gpt-4o", "isActive": True}],
                "credentialPoolStrategy": "round_robin",
            }
        ],
        "defaultModelConfig": {"model": "gpt-4o", "api_key": "sk-1"},
    }
    pooled_fp = compute_execution_fingerprint(wrapper)
    wrapper.providers_dict = {
        "providers": [
            {
                "id": "openai",
                "models": [{"id": "gpt-4o", "isActive": True}],
                "credentialPoolStrategy": "least_used",
            }
        ],
        "defaultModelConfig": {"model": "gpt-4o", "api_key": "sk-1"},
    }
    switched_fp = compute_execution_fingerprint(wrapper)
    assert pooled_fp != switched_fp
