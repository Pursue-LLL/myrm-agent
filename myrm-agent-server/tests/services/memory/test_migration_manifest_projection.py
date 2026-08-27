"""Tests for command-center migration manifest projection."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.memory.command_center.command_center_insights import (
    MemoryCommandCenterInsights,
)
from app.services.memory.imports.import_sessions import (
    DRY_RUN_STATUS_CONFIRMED,
    DRY_RUN_STATUS_EXPIRED,
    DRY_RUN_STATUS_PENDING,
    DRY_RUN_STATUS_ROLLED_BACK,
)
from app.services.migration.source.source_manifest import (
    migration_source_manifest_payload,
)


@pytest.mark.asyncio
async def test_build_migration_projects_source_manifest_and_authoritative_flag() -> None:
    ledger = MagicMock()
    ledger.migration_summary = AsyncMock(return_value=(4, 1, "partial"))
    ledger.latest_migration = AsyncMock(
        return_value=SimpleNamespace(
            metadata_json={
                "import_batch_id": "batch-123",
                "diagnostic_status": "ready",
                "diagnostic_run_id": "diag-456",
            }
        )
    )
    insights = MemoryCommandCenterInsights(
        db=MagicMock(),
        memory_manager=AsyncMock(),
        ledger=ledger,
    )

    with patch(
        "app.services.memory.command_center.command_center_insights.MemoryImportSessionService",
    ) as mock_session_service:
        mock_session_service.return_value.session_metrics = AsyncMock(
            return_value={
                DRY_RUN_STATUS_PENDING: 2,
                DRY_RUN_STATUS_CONFIRMED: 3,
                DRY_RUN_STATUS_EXPIRED: 1,
                DRY_RUN_STATUS_ROLLED_BACK: 4,
            }
        )
        migration = await insights.build_migration()

    assert migration.source_manifest_authoritative is True
    assert len(migration.source_manifest) == 8
    assert migration.source_manifest[0].import_source == "hermes"
    assert {item.id for item in migration.source_manifest} == {
        "hermes",
        "openclaw",
        "claude",
        "codex",
        "chatgpt",
        "gbrain",
        "pi",
        "plur",
    }
    chatgpt_entry = next(item for item in migration.source_manifest if item.id == "chatgpt")
    assert chatgpt_entry.discover_modes == ["zip_upload"]


@pytest.mark.asyncio
async def test_build_migration_downgrades_authoritative_when_manifest_incomplete() -> None:
    ledger = MagicMock()
    ledger.migration_summary = AsyncMock(return_value=(0, 0, "not_tracked"))
    ledger.latest_migration = AsyncMock(return_value=None)
    insights = MemoryCommandCenterInsights(
        db=MagicMock(),
        memory_manager=AsyncMock(),
        ledger=ledger,
    )
    partial_manifest = [migration_source_manifest_payload()[0]]

    with (
        patch(
            "app.services.memory.command_center.command_center_insights.MemoryImportSessionService",
        ) as mock_session_service,
        patch(
            "app.services.memory.command_center.command_center_insights.migration_source_manifest_payload",
            return_value=partial_manifest,
        ),
    ):
        mock_session_service.return_value.session_metrics = AsyncMock(
            return_value={
                DRY_RUN_STATUS_PENDING: 0,
                DRY_RUN_STATUS_CONFIRMED: 0,
                DRY_RUN_STATUS_EXPIRED: 0,
                DRY_RUN_STATUS_ROLLED_BACK: 0,
            }
        )
        migration = await insights.build_migration()

    assert migration.source_manifest_authoritative is False
    assert [item.id for item in migration.source_manifest] == ["hermes"]
