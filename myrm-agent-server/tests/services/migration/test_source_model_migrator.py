"""Tests for competitor model config migration (Hermes auxiliary + OpenClaw default)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.migration.source_model_migrator import (
    AuxiliaryMigrationResult,
    extract_hermes_auxiliary_config,
    migrate_hermes_auxiliary_models,
    migrate_openclaw_default_model,
)

MODULE = "app.services.migration.source_model_migrator"


# ---------------------------------------------------------------------------
# extract_hermes_auxiliary_config — pure function, no mock needed
# ---------------------------------------------------------------------------


class TestExtractHermesAuxiliaryConfig:
    def test_extracts_standard_tasks(self) -> None:
        config: dict[str, Any] = {
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
        config: dict[str, Any] = {
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
        config: dict[str, Any] = {
            "auxiliary": {
                "compression": "bare-string-value",
                "vision": {"provider": "openai", "model": "gpt-4o"},
            },
        }
        result = extract_hermes_auxiliary_config(config)
        assert "compression" not in result
        assert "vision" in result

    def test_skips_empty_model_string(self) -> None:
        config: dict[str, Any] = {
            "auxiliary": {
                "compression": {"provider": "openai", "model": ""},
            },
        }
        assert extract_hermes_auxiliary_config(config) == {}


# ---------------------------------------------------------------------------
# migrate_openclaw_default_model
# ---------------------------------------------------------------------------


def _mock_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(f"{MODULE}.is_local_mode", lambda: True)


def _mock_config(
    monkeypatch: pytest.MonkeyPatch,
    existing_providers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mock config_service.get/set and return a dict that captures written values."""
    captured: dict[str, Any] = {}

    record: MagicMock | None = None
    if existing_providers is not None:
        record = MagicMock()
        record.value = existing_providers

    monkeypatch.setattr(f"{MODULE}.config_service.get", AsyncMock(return_value=record))

    async def fake_set(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(f"{MODULE}.config_service.set", fake_set)
    return captured


class TestMigrateOpenclawDefaultModel:
    @pytest.mark.asyncio()
    async def test_bare_string_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        captured = _mock_config(monkeypatch)

        result = await migrate_openclaw_default_model(
            {"agents": {"defaults": {"model": "anthropic/claude-opus-4-6"}}},
        )
        assert result == "anthropic/claude-opus-4-6"
        written = captured["value"]["defaultModelConfig"]["baseModel"]["primary"]
        assert written == {"providerId": "anthropic", "model": "claude-opus-4-6"}

    @pytest.mark.asyncio()
    async def test_dict_format_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        captured = _mock_config(monkeypatch)

        result = await migrate_openclaw_default_model(
            {"agents": {"defaults": {"model": {"primary": "openai/gpt-4o"}}}},
        )
        assert result == "openai/gpt-4o"
        written = captured["value"]["defaultModelConfig"]["baseModel"]["primary"]
        assert written == {"providerId": "openai", "model": "gpt-4o"}

    @pytest.mark.asyncio()
    async def test_alias_resolution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        captured = _mock_config(monkeypatch)

        result = await migrate_openclaw_default_model({
            "agents": {
                "defaults": {
                    "model": "My Claude",
                    "models": {
                        "anthropic/claude-opus-4-6": {"alias": "My Claude"},
                    },
                },
            },
        })
        assert result == "anthropic/claude-opus-4-6"

    @pytest.mark.asyncio()
    async def test_bare_model_gets_openrouter_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        captured = _mock_config(monkeypatch)

        result = await migrate_openclaw_default_model(
            {"agents": {"defaults": {"model": "gpt-4o-mini"}}},
        )
        assert result == "openrouter/gpt-4o-mini"
        written = captured["value"]["defaultModelConfig"]["baseModel"]["primary"]
        assert written == {"providerId": "openrouter", "model": "gpt-4o-mini"}

    @pytest.mark.asyncio()
    async def test_skips_when_base_model_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        _mock_config(monkeypatch, existing_providers={
            "defaultModelConfig": {
                "baseModel": {"primary": {"providerId": "openai", "model": "gpt-4o"}},
            },
        })

        result = await migrate_openclaw_default_model(
            {"agents": {"defaults": {"model": "anthropic/claude-opus-4-6"}}},
        )
        assert result is None

    @pytest.mark.asyncio()
    async def test_returns_none_when_no_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        _mock_config(monkeypatch)

        assert await migrate_openclaw_default_model({}) is None
        assert await migrate_openclaw_default_model({"agents": {"defaults": {}}}) is None

    @pytest.mark.asyncio()
    async def test_cloud_mode_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(f"{MODULE}.is_local_mode", lambda: False)
        result = await migrate_openclaw_default_model(
            {"agents": {"defaults": {"model": "openai/gpt-4o"}}},
        )
        assert result is None


# ---------------------------------------------------------------------------
# migrate_hermes_auxiliary_models
# ---------------------------------------------------------------------------


class TestMigrateHermesAuxiliaryModels:
    @pytest.mark.asyncio()
    async def test_migrates_empty_slots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        captured = _mock_config(monkeypatch, existing_providers={})

        result = await migrate_hermes_auxiliary_models({
            "auxiliary": {
                "compression": {"provider": "openrouter", "model": "meta-llama/llama-3.3-8b-instruct"},
                "vision": {"provider": "openai", "model": "gpt-4o-mini"},
            },
        })
        assert isinstance(result, AuxiliaryMigrationResult)
        assert "liteModel" in result.migrated_slots
        assert "visionFallbackModel" in result.migrated_slots
        assert result.total_tasks_detected == 2

    @pytest.mark.asyncio()
    async def test_skips_occupied_slots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        _mock_config(monkeypatch, existing_providers={
            "defaultModelConfig": {
                "liteModel": {"model": "existing/model"},
            },
        })

        result = await migrate_hermes_auxiliary_models({
            "auxiliary": {
                "compression": {"provider": "openrouter", "model": "meta-llama/llama-3.3-8b-instruct"},
            },
        })
        assert result.migrated_slots == {}
        assert "compression" in result.skipped_tasks

    @pytest.mark.asyncio()
    async def test_skips_unknown_tasks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _mock_local(monkeypatch)
        _mock_config(monkeypatch, existing_providers={})

        result = await migrate_hermes_auxiliary_models({
            "auxiliary": {
                "unknown_hermes_task": {"provider": "openai", "model": "gpt-4o"},
            },
        })
        assert result.migrated_slots == {}
        assert "unknown_hermes_task" in result.skipped_tasks

    @pytest.mark.asyncio()
    async def test_cloud_mode_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(f"{MODULE}.is_local_mode", lambda: False)

        result = await migrate_hermes_auxiliary_models({
            "auxiliary": {
                "compression": {"provider": "openai", "model": "gpt-4o"},
            },
        })
        assert result.migrated_slots == {}
        assert result.total_tasks_detected == 0
