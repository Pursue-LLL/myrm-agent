"""Tests for Hermes moa.presets → Myrm engine_params.moa_overlay migration."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.migration.hermes_moa_migrator import (
    MoaOverlayMigrationResult,
    agent_has_moa_overlay_refs,
    build_moa_overlay_from_hermes_config,
    extract_hermes_moa_block,
    hermes_config_has_moa,
    hermes_slot_to_myrm_selection,
    migrate_hermes_moa_overlay,
    resolve_hermes_moa_preset,
)

MODULE = "app.services.migration.hermes_moa_migrator"


class TestExtractHermesMoaBlock:
    def test_returns_moa_dict(self) -> None:
        config: dict[str, Any] = {"moa": {"default_preset": "default", "presets": {}}}
        assert extract_hermes_moa_block(config) == config["moa"]

    def test_missing_or_invalid_returns_none(self) -> None:
        assert extract_hermes_moa_block({}) is None
        assert extract_hermes_moa_block({"moa": "bad"}) is None


class TestResolveHermesMoaPreset:
    def test_named_presets_use_default(self) -> None:
        moa: dict[str, Any] = {
            "default_preset": "review",
            "presets": {
                "default": {"reference_models": []},
                "review": {
                    "enabled": True,
                    "reference_models": [
                        {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b"},
                    ],
                },
            },
        }
        name, preset = resolve_hermes_moa_preset(moa)
        assert name == "review"
        assert preset is moa["presets"]["review"]

    def test_legacy_flat_config(self) -> None:
        moa: dict[str, Any] = {
            "reference_models": [
                {"provider": "openai", "model": "gpt-4o-mini", "enabled": True},
            ],
        }
        name, _preset = resolve_hermes_moa_preset(moa)
        assert name == "default"

    def test_skips_disabled_default_falls_back(self) -> None:
        moa: dict[str, Any] = {
            "default_preset": "off",
            "presets": {
                "off": {
                    "enabled": False,
                    "reference_models": [{"provider": "openai", "model": "x"}],
                },
                "live": {
                    "enabled": True,
                    "reference_models": [
                        {"provider": "anthropic", "model": "claude-3-5-sonnet"}
                    ],
                },
            },
        }
        name, _preset = resolve_hermes_moa_preset(moa)
        assert name == "live"


class TestHermesSlotToMyrmSelection:
    def test_maps_provider_and_model(self) -> None:
        result = hermes_slot_to_myrm_selection(
            {"provider": "openrouter", "model": "deepseek/deepseek-chat"},
        )
        assert result == {"providerId": "openrouter", "model": "deepseek/deepseek-chat"}

    def test_maps_openai_codex(self) -> None:
        result = hermes_slot_to_myrm_selection(
            {"provider": "openai-codex", "model": "gpt-5"},
        )
        assert result == {"providerId": "openai", "model": "gpt-5"}


class TestBuildMoaOverlayFromHermesConfig:
    def test_builds_overlay_with_refs_and_fanout(self) -> None:
        moa: dict[str, Any] = {
            "default_preset": "default",
            "privacy_filter": "display",
            "presets": {
                "default": {
                    "enabled": True,
                    "reference_models": [
                        {
                            "provider": "openrouter",
                            "model": "meta-llama/llama-3.3-70b",
                            "enabled": True,
                            "reasoning_effort": "low",
                        },
                        {
                            "provider": "anthropic",
                            "model": "claude-3-5-haiku",
                            "enabled": True,
                        },
                    ],
                    "reference_max_tokens": 800,
                    "fanout": "every_n:3",
                    "reference_temperature": 0.7,
                },
            },
        }
        overlay = build_moa_overlay_from_hermes_config(moa)
        assert overlay is not None
        assert overlay["enabled"] is True
        assert overlay["fanout"] == "every_n"
        assert overlay["every_n"] == 3
        assert overlay["privacy_filter"] == "display"
        assert overlay["reference_max_tokens"] == 800
        assert overlay["reference_reasoning_effort"] == "low"
        refs = overlay["reference_model_selections"]
        assert isinstance(refs, list)
        assert len(refs) == 2
        assert refs[0]["providerId"] == "openrouter"

    def test_rejects_recursive_moa_provider(self) -> None:
        moa: dict[str, Any] = {
            "reference_models": [{"provider": "moa", "model": "default"}],
        }
        assert build_moa_overlay_from_hermes_config(moa) is None

    def test_rejects_auto_provider_refs(self) -> None:
        moa: dict[str, Any] = {
            "reference_models": [{"provider": "auto", "model": "gpt-4o-mini"}],
        }
        assert build_moa_overlay_from_hermes_config(moa) is None


class TestHermesConfigHasMoa:
    def test_true_when_buildable(self) -> None:
        config: dict[str, Any] = {
            "moa": {
                "reference_models": [{"provider": "openai", "model": "gpt-4o-mini"}],
            },
        }
        assert hermes_config_has_moa(config) is True

    def test_false_when_empty(self) -> None:
        assert hermes_config_has_moa({}) is False


class TestAgentHasMoaOverlayRefs:
    def test_detects_existing_refs(self) -> None:
        params: dict[str, object] = {
            "moa_overlay": {
                "reference_model_selections": [
                    {"providerId": "openai", "model": "gpt-4o"}
                ],
            },
        }
        assert agent_has_moa_overlay_refs(params) is True
        assert agent_has_moa_overlay_refs({"moa_overlay": {}}) is False


class TestMigrateHermesMoaOverlay:
    @pytest.mark.asyncio
    async def test_applies_overlay_to_agent(self) -> None:
        hermes_config: dict[str, Any] = {
            "moa": {
                "reference_models": [
                    {"provider": "openai", "model": "gpt-4o-mini", "enabled": True},
                ],
                "fanout": "user_turn",
            },
        }
        mock_agent = MagicMock()
        mock_agent.engine_params = {}
        with (
            patch(
                f"{MODULE}.AgentService.get_agent_by_id", new_callable=AsyncMock
            ) as get_agent,
            patch(
                f"{MODULE}.AgentService.update_agent", new_callable=AsyncMock
            ) as update_agent,
            patch(
                f"{MODULE}.ProfileSnapshotService.save_profile_snapshot",
                new_callable=AsyncMock,
            ),
            patch(f"{MODULE}.UnitOfWork") as uow_cls,
        ):
            uow_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            uow_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            get_agent.return_value = mock_agent
            update_agent.return_value = MagicMock()

            result = await migrate_hermes_moa_overlay(hermes_config, "agent-123")

        assert isinstance(result, MoaOverlayMigrationResult)
        assert result.configured is True
        assert result.reference_count == 1
        update_agent.assert_awaited_once()
        call_args = update_agent.await_args
        assert call_args is not None
        update_payload = call_args.args[1]
        overlay = update_payload.engine_params["moa_overlay"]
        assert overlay["enabled"] is True
        assert len(overlay["reference_model_selections"]) == 1

    @pytest.mark.asyncio
    async def test_skips_when_agent_already_has_refs(self) -> None:
        hermes_config: dict[str, Any] = {
            "moa": {
                "reference_models": [{"provider": "openai", "model": "gpt-4o-mini"}],
            },
        }
        mock_agent = MagicMock()
        mock_agent.engine_params = {
            "moa_overlay": {
                "reference_model_selections": [
                    {"providerId": "anthropic", "model": "claude"}
                ],
            },
        }
        with patch(
            f"{MODULE}.AgentService.get_agent_by_id", new_callable=AsyncMock
        ) as get_agent:
            get_agent.return_value = mock_agent
            result = await migrate_hermes_moa_overlay(hermes_config, "agent-123")

        assert result.skipped_reason == "already_configured"
        assert result.configured is True

    @pytest.mark.asyncio
    async def test_skips_without_target_agent(self) -> None:
        result = await migrate_hermes_moa_overlay({"moa": {}}, "")
        assert result.skipped_reason == "no_target_agent"


class TestProviderValidation:
    @pytest.mark.asyncio
    async def test_migrate_filters_unresolvable_refs(self) -> None:
        hermes_config: dict[str, Any] = {
            "moa": {
                "reference_models": [
                    {"provider": "openai", "model": "gpt-4o-mini", "enabled": True},
                    {
                        "provider": "missing-provider",
                        "model": "ghost-model",
                        "enabled": True,
                    },
                ],
            },
        }
        mock_agent = MagicMock()
        mock_agent.engine_params = {}

        async def resolve_side_effect(ms: object, _pd: object) -> MagicMock:
            from app.services.agent.params.models import ModelSelection

            assert isinstance(ms, ModelSelection)
            if ms.provider_id == "missing-provider":
                raise ValueError("No active API key")
            return MagicMock()

        mock_configs = MagicMock()
        mock_configs.providers_dict = {
            "providers": [
                {"id": "openai", "isEnabled": True, "apiKeys": [{"key": "sk-test"}]}
            ],
        }

        with (
            patch(
                f"{MODULE}.AgentService.get_agent_by_id", new_callable=AsyncMock
            ) as get_agent,
            patch(
                f"{MODULE}.AgentService.update_agent", new_callable=AsyncMock
            ) as update_agent,
            patch(
                f"{MODULE}.ProfileSnapshotService.save_profile_snapshot",
                new_callable=AsyncMock,
            ),
            patch(f"{MODULE}.UnitOfWork") as uow_cls,
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.params._resolve_model_config",
                side_effect=resolve_side_effect,
            ),
        ):
            uow_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            uow_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            get_agent.return_value = mock_agent
            update_agent.return_value = MagicMock()

            result = await migrate_hermes_moa_overlay(hermes_config, "agent-filter")

        assert result.configured is True
        assert result.reference_count == 1
        assert result.skipped_refs == ["missing-provider/ghost-model"]
        update_payload = update_agent.await_args.args[1]
        refs = update_payload.engine_params["moa_overlay"]["reference_model_selections"]
        assert len(refs) == 1
        assert refs[0]["providerId"] == "openai"

    @pytest.mark.asyncio
    async def test_migrate_aborts_when_all_refs_unresolvable(self) -> None:
        hermes_config: dict[str, Any] = {
            "moa": {
                "reference_models": [
                    {
                        "provider": "missing-provider",
                        "model": "ghost-model",
                        "enabled": True,
                    },
                ],
            },
        }
        mock_agent = MagicMock()
        mock_agent.engine_params = {}
        mock_configs = MagicMock()
        mock_configs.providers_dict = {"providers": []}

        with (
            patch(
                f"{MODULE}.AgentService.get_agent_by_id", new_callable=AsyncMock
            ) as get_agent,
            patch(
                f"{MODULE}.AgentService.update_agent", new_callable=AsyncMock
            ) as update_agent,
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.params._resolve_model_config",
                side_effect=ValueError("No active API key"),
            ),
        ):
            get_agent.return_value = mock_agent
            result = await migrate_hermes_moa_overlay(hermes_config, "agent-none")

        assert result.configured is False
        assert result.skipped_reason == "no_resolvable_providers"
        update_agent.assert_not_awaited()


class TestApplyModelMigrationIntegration:
    @pytest.mark.asyncio
    async def test_apply_model_migration_passes_target_agent_to_moa_migrator(
        self,
    ) -> None:
        from app.services.memory.operations.crud.import_archive import (
            _apply_model_migration,
        )

        moa_block: dict[str, Any] = {
            "reference_models": [
                {"provider": "openai", "model": "gpt-4o-mini", "enabled": True}
            ],
        }
        with patch(
            "app.services.migration.hermes_moa_migrator.migrate_hermes_moa_overlay",
            new_callable=AsyncMock,
        ) as migrate_moa:
            migrate_moa.return_value = MoaOverlayMigrationResult(
                configured=True,
                reference_count=1,
                preset_name="default",
            )
            await _apply_model_migration(
                {"hermes_moa": moa_block},
                target_agent_id="agent-import-1",
            )

        migrate_moa.assert_awaited_once()
        assert migrate_moa.await_args.args[0] == {"moa": moa_block}
        assert migrate_moa.await_args.args[1] == "agent-import-1"
