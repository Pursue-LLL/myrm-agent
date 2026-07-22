"""Tests for model_resolver: enrich_model_context_window, platform headers, and resolution."""

from __future__ import annotations

from unittest.mock import patch

from app.core.channel_bridge.model_resolver import (
    _build_platform_headers,
    _fallback_model_from_providers,
    _resolve_model_max_input_tokens,
    enrich_model_context_window,
    resolve_model_config,
)
from app.core.types import ModelConfig

_MOD = "app.core.channel_bridge.model_resolver"


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

    def test_litellm_fallback(self) -> None:
        mock_info = {"max_input_tokens": 200_000}
        with patch("litellm.get_model_info", return_value=mock_info):
            result = _resolve_model_max_input_tokens("anthropic/claude-3-5-sonnet", None)
        assert result == 200_000

    def test_litellm_max_tokens_fallback(self) -> None:
        mock_info = {"max_tokens": 16_384}
        with patch("litellm.get_model_info", return_value=mock_info):
            result = _resolve_model_max_input_tokens("openai/gpt-3.5-turbo", None)
        assert result == 16_384

    def test_litellm_exception_returns_none(self) -> None:
        with patch("litellm.get_model_info", side_effect=Exception("unknown model")):
            result = _resolve_model_max_input_tokens("unknown/model", None)
        assert result is None


class TestEnrichModelContextWindow:
    def test_already_set_returns_unchanged(self) -> None:
        cfg = ModelConfig(model="gpt-4o", api_key="sk-test", max_context_tokens=64_000)
        result = enrich_model_context_window(cfg, None)
        assert result.max_context_tokens == 64_000
        assert result is cfg

    def test_enriches_from_litellm(self) -> None:
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
        )
        with patch(f"{_MOD}._resolve_model_max_input_tokens", return_value=128_000):
            result = enrich_model_context_window(cfg, {"providers": []})
        assert result.model == "gpt-4o"
        assert result.api_key == "sk-test"
        assert result.base_url == "https://custom.api"
        assert result.api_keys == ["sk-1", "sk-2"]
        assert result.max_context_tokens == 128_000


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
        assert cfg.model_kwargs is None


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
