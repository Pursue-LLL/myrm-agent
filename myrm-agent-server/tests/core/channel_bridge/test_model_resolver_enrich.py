"""Tests for model_resolver: enrich_model_context_window, platform headers, and resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.llms.catalog import known_models, register_model, store

from app.core.channel_bridge.model_resolver import (
    _build_platform_headers,
    _fallback_model_from_providers,
    _normalize_model_name,
    _resolve_model_max_input_tokens,
    enrich_model_context_window,
    resolve_model_config,
)
from app.core.types import ModelConfig

_MOD = "app.core.channel_bridge.model_resolver.enrich"


@pytest.fixture(autouse=True)
def _isolated_catalog_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})


class TestResolveModelMaxInputTokens:
    def test_returns_none_without_providers(self) -> None:
        result = _resolve_model_max_input_tokens("openai/gpt-4o", None)
        assert result is None or isinstance(result, int)

    def test_from_custom_model_info_exact_match(self) -> None:
        providers: dict[str, object] = {
            "customModelInfo": {
                "openai/gpt-4o": {"max_input_tokens": 128_000},
            },
        }
        result = _resolve_model_max_input_tokens("openai/gpt-4o", providers)
        assert result == 128_000

    def test_from_custom_model_info_fuzzy_match(self) -> None:
        providers: dict[str, object] = {
            "customModelInfo": {
                "gpt-4o": {"max_input_tokens": 128_000},
            },
        }
        result = _resolve_model_max_input_tokens("openai/gpt-4o", providers)
        assert result == 128_000

    def test_custom_model_info_invalid_value(self) -> None:
        providers: dict[str, object] = {
            "customModelInfo": {
                "openai/gpt-4o": {"max_input_tokens": -1},
            },
        }
        result = _resolve_model_max_input_tokens("openai/gpt-4o", providers)
        assert result is None or result > 0

    def test_catalog_fallback(self) -> None:
        register_model("vendor/windowed-model", {"max_input_tokens": 200_000})
        assert _resolve_model_max_input_tokens("vendor/windowed-model", None) == 200_000

    def test_a_legacy_max_tokens_entry_has_no_window(self) -> None:
        """``max_tokens`` is the output budget for part of the catalog, so it is never read as a context window."""
        register_model("vendor/legacy-model", {"max_tokens": 16_384})
        assert _resolve_model_max_input_tokens("vendor/legacy-model", None) is None

    def test_a_mixed_case_catalog_key_resolves_from_any_spelling(self) -> None:
        key, entry = next(
            (name, info)
            for name, info in known_models().items()
            if name != name.lower() and isinstance(info.get("max_input_tokens"), int)
        )
        assert _resolve_model_max_input_tokens(key, None) == entry["max_input_tokens"]
        assert _resolve_model_max_input_tokens(key.lower(), None) == entry["max_input_tokens"]

    def test_a_gateway_route_resolves_to_the_model_behind_it(self) -> None:
        register_model("routed-windowed-model", {"provider": "vendor", "max_input_tokens": 96_000})
        assert _resolve_model_max_input_tokens("my-gateway/routed-windowed-model", None) == 96_000

    def test_unknown_model_returns_none(self) -> None:
        assert _resolve_model_max_input_tokens("unknown/model", None) is None


class TestEnrichModelContextWindow:
    def test_already_set_returns_unchanged(self) -> None:
        cfg = ModelConfig(model="gpt-4o", api_key="sk-test", max_context_tokens=64_000)
        result = enrich_model_context_window(cfg, None)
        assert result.max_context_tokens == 64_000
        assert result is cfg

    def test_enriches_from_the_catalog(self) -> None:
        cfg = ModelConfig(model="gpt-4o", api_key="sk-test")
        assert cfg.max_context_tokens is None

        with patch(f"{_MOD}._resolve_model_max_input_tokens", return_value=128_000):
            result = enrich_model_context_window(cfg, None)

        assert result.max_context_tokens == 128_000
        assert result is not cfg

    def test_no_info_returns_unchanged(self) -> None:
        cfg = ModelConfig(model="unknown/model", api_key="sk-test")
        with patch(f"{_MOD}._resolve_model_max_input_tokens", return_value=None):
            result = enrich_model_context_window(cfg, None)
        assert result.max_context_tokens is None

    def test_preserves_other_fields(self) -> None:
        cfg = ModelConfig(
            model="gpt-4o",
            api_key="sk-test",
            base_url="https://custom.api",
            api_keys=["sk-1", "sk-2"],
            reasoning_effort="high",
        )
        with patch(f"{_MOD}._resolve_model_max_input_tokens", return_value=128_000):
            result = enrich_model_context_window(cfg, {"providers": []})
        assert result.model == "gpt-4o"
        assert result.api_key == "sk-test"
        assert result.base_url == "https://custom.api"
        assert result.api_keys == ["sk-1", "sk-2"]
        assert result.max_context_tokens == 128_000
        assert result.reasoning_effort == "high"


class TestBuildPlatformHeaders:
    _SETTINGS_PATH = "app.config.settings.settings"

    def test_returns_headers_for_platform_managed_key(self) -> None:
        with patch(self._SETTINGS_PATH) as mock_settings:
            mock_settings.control_plane.sandbox_id = "sb-123"
            mock_settings.control_plane.telemetry_token.get_secret_value.return_value = "tok-abc"
            result = _build_platform_headers("platform-managed")
        assert result is not None
        assert result["extra_headers"]["X-Sandbox-Id"] == "sb-123"
        assert result["extra_headers"]["X-Telemetry-Token"] == "tok-abc"

    def test_returns_none_for_byok_key(self) -> None:
        result = _build_platform_headers("sk-user-real-key")
        assert result is None

    def test_returns_blank_authorization_override_for_local_no_auth_marker(self) -> None:
        result = _build_platform_headers("__myrm_local_no_auth__")
        assert result is not None
        assert result["extra_headers"]["Authorization"] == ""

    def test_returns_none_when_sandbox_id_empty(self) -> None:
        with patch(self._SETTINGS_PATH) as mock_settings:
            mock_settings.control_plane.sandbox_id = ""
            mock_settings.control_plane.telemetry_token.get_secret_value.return_value = "tok-abc"
            result = _build_platform_headers("platform-managed")
        assert result is None


class TestResolveOverridePlatformHeaders:
    """Ensure _resolve_override injects platform headers like _fallback does."""

    _SETTINGS_PATH = "app.config.settings.settings"
    _PLATFORM_PROVIDERS: dict[str, object] = {
        "providers": [
            {
                "id": "platform-openrouter",
                "providerType": "openai-compatible",
                "isEnabled": True,
                "apiUrl": "https://relay.example.com/llm-relay/v1",
                "apiKeys": [{"key": "platform-managed", "isActive": True}],
                "enabledModels": ["google/gemma-3n-e4b-it:free"],
            }
        ],
    }

    def test_override_injects_platform_headers(self) -> None:
        with patch(self._SETTINGS_PATH) as mock_settings:
            mock_settings.control_plane.sandbox_id = "sb-456"
            mock_settings.control_plane.telemetry_token.get_secret_value.return_value = "tok-xyz"
            cfg = resolve_model_config(
                self._PLATFORM_PROVIDERS,
                model_override="platform-openrouter/google/gemma-3n-e4b-it:free",
            )
        assert cfg.model_kwargs is not None
        assert cfg.model_kwargs["extra_headers"]["X-Sandbox-Id"] == "sb-456"
        assert cfg.model_kwargs["extra_headers"]["X-Telemetry-Token"] == "tok-xyz"

    def test_override_byok_no_platform_headers(self) -> None:
        byok_providers: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "apiKeys": [{"key": "sk-real-key", "isActive": True}],
                    "enabledModels": ["gpt-4o"],
                }
            ],
        }
        cfg = resolve_model_config(byok_providers, model_override="openai/gpt-4o")
        assert not cfg.model_kwargs or "extra_headers" not in cfg.model_kwargs


class TestFallbackModelFromProviders:
    def test_resolves_model_id_field_from_default_model_config(self) -> None:
        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "xiaomi_mimo",
                    "isEnabled": True,
                    "apiUrl": "https://token-plan-cn.xiaomimimo.com/v1",
                    "apiKeys": [{"key": "tp-test", "isActive": True}],
                }
            ],
            "defaultModelConfig": {
                "baseModel": {
                    "primary": {"providerId": "xiaomi_mimo", "modelId": "mimo-v2.5-pro"},
                }
            },
        }
        cfg = _fallback_model_from_providers(providers_dict)
        assert cfg.model == "xiaomi_mimo/mimo-v2.5-pro"
        assert cfg.api_key == "tp-test"


class TestNormalizeModelName:
    def test_multi_level_prefix_folding(self) -> None:
        assert _normalize_model_name("anthropic/anthropic/claude-3-5-sonnet") == "anthropic/claude-3-5-sonnet"
        assert _normalize_model_name("anthropic-compatible/anthropic/anthropic/claude-3-5-haiku") == "anthropic/claude-3-5-haiku"
        assert _normalize_model_name("openai-compatible/openai/gpt-4o") == "openai/gpt-4o"

    def test_non_duplicate_prefix_retained(self) -> None:
        assert _normalize_model_name("meta-llama/Llama-3.3-70B-Instruct") == "meta-llama/Llama-3.3-70B-Instruct"
        assert _normalize_model_name("deepseek-ai/DeepSeek-V3") == "deepseek-ai/DeepSeek-V3"
        assert _normalize_model_name("gpt-4o") == "gpt-4o"


class TestVercelAIGatewayResolution:
    _VERCEL_PROVIDERS: dict[str, object] = {
        "providers": [
            {
                "id": "vercel_ai_gateway",
                "isEnabled": True,
                "apiUrl": "https://ai-gateway.vercel.sh/v1",
                "apiKeys": [{"key": "vcel-test-key", "isActive": True}],
                "enabledModels": [
                    "anthropic/claude-3-5-sonnet",
                    "openai/gpt-4o",
                ],
            }
        ],
    }

    def test_override_with_namespaced_model_resolves_openai_wire(self) -> None:
        cfg = resolve_model_config(
            self._VERCEL_PROVIDERS,
            model_override="vercel_ai_gateway/anthropic/claude-3-5-sonnet",
        )
        assert cfg.model == "openai/anthropic/claude-3-5-sonnet"
        assert cfg.base_url == "https://ai-gateway.vercel.sh/v1"
        assert cfg.api_key == "vcel-test-key"
        assert cfg.model_kwargs is not None
        headers = cfg.model_kwargs.get("extra_headers")
        assert isinstance(headers, dict)
        assert headers.get("HTTP-Referer") == "https://myrm.ai"
        assert headers.get("X-Title") == "Myrm Agent"

    def test_fallback_model_from_providers_for_vercel_gateway(self) -> None:
        providers_dict: dict[str, object] = {
            "providers": self._VERCEL_PROVIDERS["providers"],
            "defaultModelConfig": {
                "baseModel": {
                    "primary": {"providerId": "vercel_ai_gateway", "modelId": "anthropic/claude-3-5-sonnet"},
                }
            },
        }
        cfg = _fallback_model_from_providers(providers_dict)
        assert cfg.model == "openai/anthropic/claude-3-5-sonnet"
        assert cfg.base_url == "https://ai-gateway.vercel.sh/v1"
        assert cfg.model_kwargs is not None
        headers = cfg.model_kwargs.get("extra_headers")
        assert isinstance(headers, dict)
        assert headers.get("HTTP-Referer") == "https://myrm.ai"
        assert headers.get("X-Title") == "Myrm Agent"


class TestProviderOAuthResolution:
    """Test model resolution when provider has OAuth token instead of plain API key."""

    def test_xai_oauth_token_fallback_and_base_url(self) -> None:
        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "xai",
                    "isEnabled": True,
                    "apiUrl": "https://api.x.ai/v1",
                    "apiKeys": [],  # No plain API key
                    "_oauthToken": "xai-oauth-test-token-xyz",
                    "_oauthBaseUrl": "https://api.x.ai/v1",
                    "enabledModels": ["grok-2", "grok-2-mini"],
                }
            ],
            "defaultModelConfig": {
                "baseModel": {
                    "primary": {"providerId": "xai", "model": "grok-2"},
                }
            },
        }
        cfg = _fallback_model_from_providers(providers_dict)
        assert cfg.model == "xai/grok-2"
        assert cfg.api_key == "xai-oauth-test-token-xyz"
        assert cfg.base_url == "https://api.x.ai/v1"
