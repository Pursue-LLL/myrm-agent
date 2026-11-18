"""Tests for the pure parts of competitor model config migration (Hermes auxiliary + OpenClaw default)."""

from __future__ import annotations

import pytest

from app.services.migration.source.source_model_migrator import (
    _route_id_to_primary_selection,
    extract_hermes_auxiliary_config,
    extract_openclaw_default_model_config,
)

# ---------------------------------------------------------------------------
# _route_id_to_primary_selection — pure function, no mock needed
# ---------------------------------------------------------------------------


class TestRouteIdToPrimarySelection:
    def test_the_leading_segment_is_the_provider(self) -> None:
        assert _route_id_to_primary_selection("anthropic/claude-opus-4-6") == {
            "providerId": "anthropic",
            "model": "claude-opus-4-6",
        }

    def test_only_the_first_slash_splits_provider_from_model(self) -> None:
        assert _route_id_to_primary_selection("openrouter/meta-llama/llama-3.3-8b-instruct") == {
            "providerId": "openrouter",
            "model": "meta-llama/llama-3.3-8b-instruct",
        }

    def test_a_bare_model_id_is_attributed_to_openrouter(self) -> None:
        assert _route_id_to_primary_selection("gpt-4o-mini") == {"providerId": "openrouter", "model": "gpt-4o-mini"}


# ---------------------------------------------------------------------------
# extract_hermes_auxiliary_config — pure function, no mock needed
# ---------------------------------------------------------------------------


class TestExtractHermesAuxiliaryConfig:
    def test_extracts_standard_tasks(self) -> None:
        config: dict[str, object] = {
            "auxiliary": {
                "compression": {"provider": "openrouter", "model": "meta-llama/llama-3.3-8b-instruct"},
                "vision": {"provider": "openai", "model": "gpt-4o-mini"},
            },
        }
        result = extract_hermes_auxiliary_config(config)
        assert result == {
            "compression": {"provider": "openrouter", "model": "meta-llama/llama-3.3-8b-instruct"},
            "vision": {"provider": "openai", "model": "gpt-4o-mini"},
        }

    def test_auto_provider_normalised(self) -> None:
        config: dict[str, object] = {
            "auxiliary": {
                "compression": {"provider": "auto", "model": "gpt-4o-mini"},
                "vision": {"provider": "main", "model": "claude-3-haiku"},
            },
        }
        result = extract_hermes_auxiliary_config(config)
        assert result["compression"]["provider"] == "auto"
        assert result["vision"]["provider"] == "auto"

    def test_missing_auxiliary_returns_empty(self) -> None:
        assert extract_hermes_auxiliary_config({}) == {}
        assert extract_hermes_auxiliary_config({"auxiliary": "not-a-dict"}) == {}

    def test_skips_non_dict_task_entries(self) -> None:
        config: dict[str, object] = {
            "auxiliary": {
                "compression": "bare-string-value",
                "vision": {"provider": "openai", "model": "gpt-4o"},
            },
        }
        result = extract_hermes_auxiliary_config(config)
        assert "compression" not in result
        assert "vision" in result

    def test_skips_empty_model_string(self) -> None:
        config: dict[str, object] = {
            "auxiliary": {
                "compression": {"provider": "openai", "model": ""},
            },
        }
        assert extract_hermes_auxiliary_config(config) == {}


# ---------------------------------------------------------------------------
# extract_openclaw_default_model_config — pure function, no mock needed
# ---------------------------------------------------------------------------


class TestExtractOpenclawDefaultModelConfig:
    def test_keeps_only_the_fields_the_migration_reads(self) -> None:
        defaults: dict[str, object] = {
            "model": {"primary": "anthropic/claude-opus-4-6"},
            "models": {"anthropic/claude-opus-4-6": {"alias": "opus"}},
            "memorySearch": {"remote": {"apiKey": "PLACEHOLDER_MEMORY_SEARCH_KEY"}},
        }
        result = extract_openclaw_default_model_config({"agents": {"defaults": defaults}})
        assert result == {"model": defaults["model"], "models": defaults["models"]}

    @pytest.mark.parametrize(
        "config",
        [{}, {"agents": ["x"]}, {"agents": {"defaults": "x"}}, {"agents": {"defaults": {"sandbox": {}}}}],
    )
    def test_a_missing_or_malformed_block_is_empty(self, config: dict[str, object]) -> None:
        assert extract_openclaw_default_model_config(config) == {}
