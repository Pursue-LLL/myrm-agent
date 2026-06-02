"""Tests for enrich_model_context_window and _resolve_model_max_input_tokens."""

from __future__ import annotations

from unittest.mock import patch

from app.core.channel_bridge.model_resolver import (
    _resolve_model_max_input_tokens,
    enrich_model_context_window,
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
