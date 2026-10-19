"""Coverage for the post-import side effects and readiness recheck handler."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.archive import (
    MemoryImportReadiness,
    MemoryImportReadinessRecheckRequest,
)
from app.services.memory.operations.crud.import_flows.side_effects import (
    _apply_model_migration,
    _resolve_post_import_moa_overlay_configured,
    _write_migrated_mcp_configs,
    recheck_import_readiness,
)
from tests.services.memory.import_flows.support import session_context


@pytest.mark.asyncio
async def test_recheck_rejects_a_blank_batch_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await recheck_import_readiness(MemoryImportReadinessRecheckRequest(import_batch_id="   "))

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_recheck_keeps_the_verdict_when_persistence_fails() -> None:
    readiness = MemoryImportReadiness(status="warning")
    service = SimpleNamespace(
        resolve_live_import_readiness=AsyncMock(return_value=readiness),
        save_post_import_readiness=AsyncMock(side_effect=RuntimeError("ledger locked")),
    )

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.side_effects.MemoryImportSessionService",
            return_value=service,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.side_effects.get_session",
            session_context(cast(AsyncSession, SimpleNamespace())),
        ),
    ):
        response = await recheck_import_readiness(MemoryImportReadinessRecheckRequest(import_batch_id=" batch-1 "))

    assert response.import_batch_id == "batch-1"
    assert response.readiness is readiness


@pytest.mark.asyncio
async def test_mcp_config_writer_skips_existing_and_unnamed_servers() -> None:
    from app.services.config.service import config_service

    record = SimpleNamespace(value=[{"name": "fs"}])
    set_mock = AsyncMock()

    with (
        patch.object(config_service, "get", AsyncMock(return_value=record)),
        patch.object(config_service, "set", set_mock),
    ):
        inserted = await _write_migrated_mcp_configs(
            [{"name": "fs"}, {"name": " "}, {"name": "db", "command": "run"}],
        )

    assert inserted == 1
    written = set_mock.await_args.args[1]
    assert written[0] == {"name": "fs"}
    assert written[-1] == {"name": "db", "command": "run", "enabled": False}


@pytest.mark.asyncio
async def test_moa_overlay_prefers_the_migrated_agent_then_the_payload() -> None:
    agent = SimpleNamespace(engine_params={"moa": {"models": ["a"]}})
    with (
        patch(
            "app.services.agent.agent_service.AgentService.get_agent_by_id",
            AsyncMock(return_value=agent),
        ),
        patch(
            "app.services.migration.hermes.hermes_moa_migrator.agent_has_moa_overlay_refs",
            return_value=True,
        ),
    ):
        assert await _resolve_post_import_moa_overlay_configured("agent-1", {}) is True

    with patch(
        "app.services.migration.hermes.hermes_moa_migrator.build_moa_overlay_from_hermes_config",
        return_value=object(),
    ):
        assert await _resolve_post_import_moa_overlay_configured(None, {"hermes_moa": {"models": ["a"]}}) is False

    with patch(
        "app.services.migration.hermes.hermes_moa_migrator.build_moa_overlay_from_hermes_config",
        return_value=None,
    ):
        assert await _resolve_post_import_moa_overlay_configured(None, {"hermes_moa": {"models": []}}) is True


@pytest.mark.asyncio
async def test_model_migration_applies_every_lane_and_swallows_failures() -> None:
    auxiliary = AsyncMock(return_value=SimpleNamespace(migrated_slots=["aux"]))
    moa = AsyncMock(return_value=SimpleNamespace(configured=True, reference_count=2, preset_name="preset"))
    openclaw = AsyncMock(return_value="openai/gpt")

    with (
        patch("app.services.migration.source.source_model_migrator.migrate_hermes_auxiliary_models", auxiliary),
        patch("app.services.migration.hermes.hermes_moa_migrator.migrate_hermes_moa_overlay", moa),
        patch("app.services.migration.source.source_model_migrator.migrate_openclaw_default_model", openclaw),
    ):
        await _apply_model_migration(
            {
                "hermes_auxiliary": {"x": "y"},
                "hermes_moa": {"models": ["a"]},
                "openclaw_agents_defaults": {"model": "openai/gpt"},
            },
            target_agent_id="agent-1",
        )

    auxiliary.assert_awaited_once()
    moa.assert_awaited_once()
    openclaw.assert_awaited_once()

    failing = AsyncMock(side_effect=RuntimeError("provider down"))
    failing_moa = AsyncMock(side_effect=RuntimeError("overlay rejected"))
    with (
        patch("app.services.migration.source.source_model_migrator.migrate_hermes_auxiliary_models", failing),
        patch("app.services.migration.source.source_model_migrator.migrate_openclaw_default_model", failing),
        patch("app.services.migration.hermes.hermes_moa_migrator.migrate_hermes_moa_overlay", failing_moa),
    ):
        await _apply_model_migration(
            {
                "hermes_auxiliary": {"x": "y"},
                "hermes_moa": {"models": ["a"]},
                "openclaw_agents_defaults": {"model": "x"},
            },
            target_agent_id="agent-1",
        )

    failing_moa.assert_awaited_once()
