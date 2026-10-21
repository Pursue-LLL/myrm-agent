"""Tests for the channel-bridge config parsers."""

from __future__ import annotations

# ── session_policy_from_agent_dict ────────────────────────────────
from app.channels.types import SessionResetMode  # noqa: E402
from app.core.channel_bridge.config_parsers import (  # noqa: E402
    extract_session_policy,
    session_policy_from_agent_dict,
)


class TestSessionPolicyFromAgentDict:
    def test_daily_mode_with_defaults(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 4, "idle_minutes": 120}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY
        assert policy.daily_reset_hour == 4
        assert policy.idle_minutes == 120
        assert policy.notify_on_reset is True

    def test_persistent_mode(self) -> None:
        raw = {"mode": "persistent"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.PERSISTENT
        assert policy.daily_reset_hour == 4
        assert policy.idle_minutes == 120

    def test_idle_mode_custom_minutes(self) -> None:
        raw = {"mode": "idle", "idle_minutes": 30}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.IDLE
        assert policy.idle_minutes == 30

    def test_invalid_mode_falls_back_to_daily(self) -> None:
        raw = {"mode": "nonexistent_mode"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY

    def test_missing_mode_defaults_to_daily(self) -> None:
        raw: dict[str, object] = {}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY

    def test_float_values_coerced_to_int(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 6.0, "idle_minutes": 60.0}
        policy = session_policy_from_agent_dict(raw)
        assert policy.daily_reset_hour == 6
        assert policy.idle_minutes == 60

    def test_custom_reset_hour(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 23}
        policy = session_policy_from_agent_dict(raw)
        assert policy.daily_reset_hour == 23

    def test_notify_on_reset_false(self) -> None:
        raw = {"mode": "daily", "notify_on_reset": False}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is False

    def test_notify_on_reset_true_explicit(self) -> None:
        raw = {"mode": "daily", "notify_on_reset": True}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is True

    def test_notify_on_reset_missing_defaults_true(self) -> None:
        raw = {"mode": "daily"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is True


class TestExtractSessionPolicy:
    def test_none_returns_default(self) -> None:
        policy = extract_session_policy(None)
        assert policy.mode == SessionResetMode.DAILY

    def test_missing_key_returns_default(self) -> None:
        policy = extract_session_policy({"other": "data"})
        assert policy.mode == SessionResetMode.DAILY

    def test_valid_policy_parsed(self) -> None:
        raw = {"sessionPolicy": {"mode": "idle", "idleMinutes": 45}}
        policy = extract_session_policy(raw)
        assert policy.mode == SessionResetMode.IDLE
        assert policy.idle_minutes == 45

    def test_persistent_mode(self) -> None:
        raw = {"sessionPolicy": {"mode": "persistent"}}
        policy = extract_session_policy(raw)
        assert policy.mode == SessionResetMode.PERSISTENT

    def test_notify_on_reset_false(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily", "notifyOnReset": False}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is False

    def test_notify_on_reset_true(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily", "notifyOnReset": True}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is True

    def test_notify_on_reset_missing_defaults_true(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily"}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is True


class TestExtractVisionFallbackModelConfig:
    def test_returns_none_for_empty_providers(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        assert extract_vision_fallback_model_config(None) is None
        assert extract_vision_fallback_model_config({}) is None

    def test_resolves_vision_fallback_from_default_model_config(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                }
            },
        }
        cfg = extract_vision_fallback_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "openai/gpt-4o-mini"
        assert cfg.api_key == "sk-vision"

    def test_returns_none_when_provider_disabled(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": False,
                    "apiKeys": [{"key": "sk-vision", "isActive": True}],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                }
            },
        }
        assert extract_vision_fallback_model_config(providers_dict) is None


class TestExtractVisionFallbackModelConfigs:
    def test_builds_chain_with_main_agent_when_vision_capable(self) -> None:
        from app.core.channel_bridge.config_parsers import (
            build_vision_fallback_config_chain,
            extract_vision_fallback_model_configs,
        )
        from app.core.types import ModelConfig

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini", "gpt-4o"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                },
                "baseModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o"},
                },
            },
        }

        chain = extract_vision_fallback_model_configs(providers_dict)
        assert len(chain) == 2
        assert chain[0].model == "openai/gpt-4o-mini"
        assert chain[1].model == "openai/gpt-4o"

        main_cfg = ModelConfig(
            model="openai/gpt-4o",
            api_key="sk-main",
            supports_vision=True,
        )
        custom_chain = build_vision_fallback_config_chain(
            providers_dict,
            primary_override=chain[0],
            main_model_cfg=main_cfg,
        )
        assert len(custom_chain) == 2
        assert custom_chain[-1].api_key == "sk-main"

    def test_builds_chain_with_model_slot_fallback(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_configs

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini", "gpt-4o"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o-mini"},
                    "fallback": {"providerId": "openai", "model": "gpt-4o"},
                },
            },
        }

        chain = extract_vision_fallback_model_configs(providers_dict)
        assert len(chain) == 2
        assert chain[0].model == "openai/gpt-4o-mini"
        assert chain[1].model == "openai/gpt-4o"

    def test_build_vision_fallback_engine_from_providers(self) -> None:
        from app.core.channel_bridge.config_parsers import build_vision_fallback_engine_from_providers

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o-mini"},
                },
            },
        }

        engine = build_vision_fallback_engine_from_providers(providers_dict)
        assert engine is not None
        assert len(engine.fallback_configs) == 1
        assert engine.fallback_configs[0].model == "openai/gpt-4o-mini"

    def test_extract_slot_fallback_chain_ordered_and_resilient(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_slot_fallback_chain

        providers_dict = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-1",
                    "enabledModels": ["gpt-4o"],
                },
                {
                    "id": "anthropic",
                    "isEnabled": False,  # Disabled provider should be skipped
                    "providerType": "anthropic",
                    "apiKey": "sk-2",
                    "enabledModels": ["claude-3-5-sonnet"],
                },
                {
                    "id": "deepseek",
                    "isEnabled": True,
                    "providerType": "deepseek",
                    "apiUrl": "https://api.deepseek.com/v1",
                    "apiKey": "sk-3",
                    "enabledModels": ["deepseek-chat"],
                },
            ],
        }

        slot = {
            "fallbacks": [
                {"providerId": "openai", "model": "gpt-4o"},
                {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                {"providerId": "deepseek", "model": "deepseek-chat"},
            ]
        }

        configs = extract_slot_fallback_chain(slot, providers_dict)
        assert len(configs) == 2
        assert configs[0].model == "openai/gpt-4o"
        assert configs[1].model == "deepseek/deepseek-chat"

    def test_slot_fallback_chain_applies_wire_protocol_for_opencode(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_slot_fallback_chain

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "opencode_go",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://opencode.ai/zen/go/v1",
                    "apiKey": "sk-opencode",
                    "enabledModels": ["muse-spark-1.2-contributor"],
                }
            ],
        }
        slot = {
            "fallbacks": [
                {"providerId": "opencode_go", "model": "muse-spark-1.2-contributor"},
            ]
        }

        configs = extract_slot_fallback_chain(slot, providers_dict)
        assert len(configs) == 1
        assert configs[0].wire_protocol == "responses"


class TestBackgroundEvolutionModelExtraction:
    """Tests for extract_background_evolution_model_configs 3-tier adaptive fallback."""

    def test_extracts_explicit_background_evolution_model(self) -> None:
        from app.core.channel_bridge.config_parsers import (
            extract_background_evolution_model_config,
            extract_background_evolution_model_configs,
        )

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-1",
                    "enabledModels": ["gpt-4o", "gpt-4o-mini"],
                },
                {
                    "id": "deepseek",
                    "isEnabled": True,
                    "apiUrl": "https://api.deepseek.com/v1",
                    "apiKey": "sk-2",
                    "enabledModels": ["deepseek-chat"],
                },
            ],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o"}},
                "liteModel": {"primary": {"providerId": "openai", "model": "gpt-4o-mini"}},
                "backgroundEvolutionModel": {"primary": {"providerId": "deepseek", "model": "deepseek-chat"}},
            },
        }

        configs = extract_background_evolution_model_configs(providers_dict)
        assert len(configs) >= 1
        assert configs[0].model == "deepseek/deepseek-chat"

        primary = extract_background_evolution_model_config(providers_dict)
        assert primary is not None
        assert primary.model == "deepseek/deepseek-chat"

    def test_falls_back_to_lite_model_when_evolution_model_unset(self) -> None:
        from app.core.channel_bridge.config_parsers import (
            extract_background_evolution_model_config,
        )

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-1",
                    "enabledModels": ["gpt-4o", "gpt-4o-mini"],
                },
            ],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o"}},
                "liteModel": {"primary": {"providerId": "openai", "model": "gpt-4o-mini"}},
                "backgroundEvolutionModel": None,
            },
        }

        cfg = extract_background_evolution_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "openai/gpt-4o-mini"

    def test_falls_back_to_base_model_when_both_evolution_and_lite_unset(self) -> None:
        from app.core.channel_bridge.config_parsers import (
            extract_background_evolution_model_config,
        )

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-1",
                    "enabledModels": ["gpt-4o"],
                },
            ],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o"}},
                "liteModel": None,
                "backgroundEvolutionModel": None,
            },
        }

        cfg = extract_background_evolution_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "openai/gpt-4o"

    def test_extract_model_config_with_xai_oauth_fallback(self) -> None:
        """测试在无 API Key 仅有 xAI OAuth Token 时，resolve_model_config 成功提取 token 作为 api_key"""
        from app.core.channel_bridge.model_resolver import resolve_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "xai",
                    "isEnabled": True,
                    "apiUrl": "https://api.x.ai/v1",
                    "apiKeys": [],
                    "_oauthToken": "xai-oauth-live-access-token",
                    "_oauthBaseUrl": "https://api.x.ai/v1",
                    "enabledModels": ["grok-2"],
                },
            ],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "xai", "model": "grok-2"}},
            },
        }

        cfg = resolve_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "xai/grok-2"
        assert cfg.api_key == "xai-oauth-live-access-token"
        assert cfg.base_url == "https://api.x.ai/v1"

    def test_extract_model_config_api_key_takes_precedence_over_oauth_token(self) -> None:
        """测试当同时存在 API Key 和 OAuth Token 时，API Key 优先被采用"""
        from app.core.channel_bridge.model_resolver import resolve_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "xai",
                    "isEnabled": True,
                    "apiUrl": "https://api.x.ai/v1",
                    "apiKeys": [{"key": "xai-real-api-key", "isActive": True}],
                    "_oauthToken": "xai-oauth-token-fallback",
                    "_oauthBaseUrl": "https://api.x.ai/v1",
                    "enabledModels": ["grok-2"],
                },
            ],
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "xai", "model": "grok-2"}},
            },
        }

        cfg = resolve_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "xai/grok-2"
        assert cfg.api_key == "xai-real-api-key"
