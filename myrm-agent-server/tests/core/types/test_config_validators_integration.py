"""Integration tests for config auto-healing across the full request pipeline.

Validates that Pydantic field validators correctly clean dirty input data
as it flows through the real resolution chain:
  ModelSelection (API boundary) → _resolve_model_config → ModelConfig (cleaned)
  providers_dict (DB/frontend) → _fallback_model_from_providers → ModelConfig (cleaned)
  providers_dict (DB/frontend) → _resolve_override → ModelConfig (cleaned)

These tests use REAL resolver functions (no mocks on the cleaning path) to prove
that config self-healing works end-to-end in production scenarios.
"""

from __future__ import annotations

import pytest

from app.core.types import MCPServerConfig, ModelConfig
from app.services.agent.params.models import ModelSelection


def _make_providers_dict(
    *,
    provider_id: str = "openai",
    api_key: str = "sk-test-key-123",
    api_url: str = "https://api.openai.com/v1",
    model: str = "gpt-4o",
    provider_type: str = "openai",
) -> dict[str, object]:
    """Build a minimal providers_dict simulating WebUI DB config.

    Uses the real apiKeys format (list of {key, isActive} dicts) that
    _extract_all_active_keys expects.
    """
    return {
        "providers": [
            {
                "id": provider_id,
                "providerType": provider_type,
                "isEnabled": True,
                "apiKeys": [{"key": api_key, "isActive": True}],
                "apiUrl": api_url,
                "enabledModels": [model],
            }
        ],
        "defaultModelConfig": {
            "baseModel": {
                "primary": {
                    "providerId": provider_id,
                    "model": model,
                }
            }
        },
    }


class TestModelSelectionToModelConfigIntegration:
    """Prove that dirty data in ModelSelection gets cleaned via ModelConfig validators."""

    def test_base_url_trailing_slash_cleaned_via_resolver(self) -> None:
        """Simulates frontend sending baseUrl with trailing slash."""
        from app.core.channel_bridge.model_resolver import _resolve_override

        providers = _make_providers_dict(api_url="https://api.openai.com/v1/")
        cfg = _resolve_override(providers, "openai/gpt-4o")
        assert cfg is not None
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_base_url_whitespace_cleaned_via_resolver(self) -> None:
        """Simulates DB storing apiUrl with leading/trailing whitespace."""
        from app.core.channel_bridge.model_resolver import _resolve_override

        providers = _make_providers_dict(api_url="  https://api.openai.com/v1  ")
        cfg = _resolve_override(providers, "openai/gpt-4o")
        assert cfg is not None
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_base_url_whitespace_and_slash_cleaned_via_resolver(self) -> None:
        """Worst case: whitespace + trailing slash combined."""
        from app.core.channel_bridge.model_resolver import _resolve_override

        providers = _make_providers_dict(api_url="  https://api.openai.com/v1/  ")
        cfg = _resolve_override(providers, "openai/gpt-4o")
        assert cfg is not None
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_empty_base_url_becomes_none_via_resolver(self) -> None:
        """Empty string apiUrl in provider row → None in ModelConfig."""
        from app.core.channel_bridge.model_resolver import _resolve_override

        providers = _make_providers_dict(api_url="")
        cfg = _resolve_override(providers, "openai/gpt-4o")
        assert cfg is not None
        assert cfg.base_url is None

    def test_api_key_whitespace_cleaned_via_resolver(self) -> None:
        """API key with accidental whitespace gets stripped."""
        from app.core.channel_bridge.model_resolver import _resolve_override

        providers = _make_providers_dict(api_key="  sk-test-key-123  ")
        cfg = _resolve_override(providers, "openai/gpt-4o")
        assert cfg is not None
        assert cfg.api_key == "sk-test-key-123"


class TestFallbackModelResolutionIntegration:
    """Prove that _fallback_model_from_providers also triggers cleaning."""

    def test_fallback_cleans_trailing_slash(self) -> None:
        from app.core.channel_bridge.model_resolver import _fallback_model_from_providers

        providers = _make_providers_dict(api_url="https://api.openai.com/v1/")
        cfg = _fallback_model_from_providers(providers)
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_fallback_cleans_whitespace_url(self) -> None:
        from app.core.channel_bridge.model_resolver import _fallback_model_from_providers

        providers = _make_providers_dict(api_url="  https://api.openai.com/v1/  ")
        cfg = _fallback_model_from_providers(providers)
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_fallback_cleans_api_key(self) -> None:
        from app.core.channel_bridge.model_resolver import _fallback_model_from_providers

        providers = _make_providers_dict(api_key="  sk-my-key  ")
        cfg = _fallback_model_from_providers(providers)
        assert cfg.api_key == "sk-my-key"


class TestModelSelectionBaseUrlPassthrough:
    """Prove that ModelSelection.base_url flows through _resolve_model_config and gets cleaned."""

    @pytest.mark.asyncio
    async def test_selection_base_url_cleaned(self) -> None:
        from app.services.agent.params.resolvers import _resolve_model_config

        selection = ModelSelection(
            provider_id="openai",
            model="gpt-4o",
            base_url="https://custom-api.example.com/v1/ ",
        )
        providers = _make_providers_dict()
        cfg = await _resolve_model_config(selection, providers)
        assert cfg.base_url == "https://custom-api.example.com/v1"

    @pytest.mark.asyncio
    async def test_selection_empty_base_url_uses_provider(self) -> None:
        from app.services.agent.params.resolvers import _resolve_model_config

        selection = ModelSelection(
            provider_id="openai",
            model="gpt-4o",
            base_url="",
        )
        providers = _make_providers_dict(api_url="https://api.openai.com/v1/")
        cfg = await _resolve_model_config(selection, providers)
        assert cfg.base_url == "https://api.openai.com/v1"


class TestMCPServerConfigIntegration:
    """Prove MCPServerConfig validator works in realistic construction scenarios."""

    def test_sse_config_url_cleaned(self) -> None:
        """Simulate frontend saving MCP server with dirty URL."""
        config_data = {
            "name": "my-mcp-server",
            "type": "sse",
            "url": "  https://mcp.example.com/sse/  ",
            "description": "Test MCP",
        }
        cfg = MCPServerConfig.model_validate(config_data)
        assert cfg.url == "https://mcp.example.com/sse"

    def test_streamable_http_url_cleaned(self) -> None:
        config_data = {
            "name": "http-mcp",
            "type": "streamable_http",
            "url": "https://api.example.com/mcp/ ",
            "description": "Streamable HTTP MCP",
        }
        cfg = MCPServerConfig.model_validate(config_data)
        assert cfg.url == "https://api.example.com/mcp"

    def test_camel_case_url_cleaned(self) -> None:
        """Frontend sends camelCase field names."""
        config_data = {
            "name": "camel-mcp",
            "type": "sse",
            "url": "https://mcp.example.com/ ",
        }
        cfg = MCPServerConfig.model_validate(config_data)
        assert cfg.url == "https://mcp.example.com"


class TestRealWorldDirtyInputScenarios:
    """Reproduce common user mistakes observed in production."""

    def test_copy_paste_url_with_newline_chars(self) -> None:
        """User copies URL from docs with trailing spaces/tabs."""
        cfg = ModelConfig(
            model="gpt-4o",
            api_key="sk-key123",
            base_url="https://api.openai.com/v1\t  ",
        )
        assert cfg.base_url == "https://api.openai.com/v1"

    def test_url_with_only_slashes(self) -> None:
        """Accidental input of just slashes."""
        cfg = ModelConfig(model="m", api_key="k", base_url="///")
        assert cfg.base_url is None

    def test_model_name_with_leading_space(self) -> None:
        """Model picker sometimes adds leading space."""
        cfg = ModelConfig(model=" gpt-4o-mini", api_key="k")
        assert cfg.model == "gpt-4o-mini"

    def test_api_key_with_trailing_newline(self) -> None:
        """Paste from terminal often includes trailing newline."""
        cfg = ModelConfig(model="m", api_key="sk-abc\n")
        assert cfg.api_key == "sk-abc"

    def test_frozen_model_config_still_validates(self) -> None:
        """ModelConfig is frozen=True, validators must run BEFORE freeze."""
        cfg = ModelConfig(
            model="  gpt-4  ",
            api_key="  key  ",
            base_url="  https://api.example.com/  ",
        )
        assert cfg.model == "gpt-4"
        assert cfg.api_key == "key"
        assert cfg.base_url == "https://api.example.com"
        with pytest.raises(Exception):
            cfg.model = "other"  # type: ignore[misc]
