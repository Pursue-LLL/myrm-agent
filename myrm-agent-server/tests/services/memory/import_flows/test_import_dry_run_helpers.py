"""Coverage for dry-run source normalization, preview rows and the paste lane."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.archive import (
    MemoryImportDryRunRequest,
    MemoryImportMigrationOptions,
)
from app.services.memory.operations.crud.import_flows.dry_run import dry_run_import_memories
from app.services.memory.operations.crud.import_flows.dry_run_preview import _cron_lane
from app.services.memory.operations.crud.import_flows.dry_run_source import (
    LoadedSource,
    build_side_channels,
    load_competitor_source,
)
from app.services.migration.source.source_migration_types import (
    MigrationWizardOptions,
    SourceInstructionPlan,
)
from app.services.migration.source.source_payload_loader import (
    MAX_PENDING_SKILLS,
    MigrationSourceAccessError,
)
from tests.services.memory.import_flows.support import session_context


def test_cron_lane_flags_a_skipped_only_plan() -> None:
    lane = _cron_lane({"importable": [], "skipped": [{"name": "a"}, {"name": "b"}]})

    assert lane.status == "warning"
    assert lane.detail_parts[0].code == "cron_skipped"
    assert lane.detail_parts[0].params == {"skipped": 2}

    missing = _cron_lane(None)

    assert missing.status == "missing"
    assert missing.detail_parts[0].code == "cron_none"


def test_load_competitor_source_maps_access_errors_to_http_422() -> None:
    with (
        patch(
            "app.services.migration.source.source_payload_loader.load_source_payload",
            side_effect=MigrationSourceAccessError("outside the archive root"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        load_competitor_source({"root": "/etc"}, None)

    assert exc_info.value.status_code == 422


def test_load_competitor_source_caps_the_pending_skill_list() -> None:
    skills = [{"name": f"skill-{index}"} for index in range(MAX_PENDING_SKILLS + 3)]
    instruction_plan = SourceInstructionPlan(competitor="hermes")

    with (
        patch(
            "app.services.migration.source.source_payload_loader.load_source_payload",
            return_value={"_source": "hermes"},
        ),
        patch(
            "app.services.migration.source.source_payload_loader.extract_pending_skills",
            return_value=skills,
        ),
        patch(
            "app.services.migration.source.source_payload_loader.build_coverage_items",
            return_value=[],
        ),
        patch(
            "app.services.migration.source.source_payload_split.build_instruction_plan",
            return_value=instruction_plan,
        ),
        patch(
            "app.services.migration.source.source_payload_split.extract_memory_payload",
            return_value={"data": {}},
        ),
        patch(
            "app.services.migration.source.source_payload_split.has_api_keys",
            return_value=False,
        ),
        patch(
            "app.services.memory.imports.import_adapters.resolve_migration_source",
            return_value="hermes",
        ),
    ):
        loaded = load_competitor_source({"root": "/tmp/hermes"}, None)

    assert loaded.pending_skills_total == MAX_PENDING_SKILLS + 3
    assert len(loaded.pending_skills) == MAX_PENDING_SKILLS
    assert loaded.competitor == "hermes"


def test_build_side_channels_reads_openclaw_defaults_and_filters_sessions() -> None:
    loaded = LoadedSource(
        loaded_payload={
            "openclaw_config": {"agents": {"defaults": {"model": "openai/gpt"}}},
            "sessions": ["not-a-session", {"session_id": "session-1"}],
            "hermes_cron_plan": ["not-a-plan"],
        },
        instruction_plan=SourceInstructionPlan(competitor="openclaw"),
        migration_opts=MigrationWizardOptions(),
        import_payload={},
        resolved_source="openclaw",
        competitor="openclaw",
        source_has_api_keys=False,
        pending_skills=[],
        pending_skills_total=0,
        coverage_items=[],
    )

    with patch(
        "app.services.migration.workspace_bind_candidates.discover_workspace_bind_candidates",
        return_value=[],
    ):
        channels = build_side_channels(loaded)

    assert channels.model_migration_payload == {
        "openclaw_agents_defaults": {"model": "openai/gpt"},
    }
    assert channels.sessions == [{"session_id": "session-1"}]
    assert channels.cron_plan_raw is None
    assert channels.mcp_servers_preview == []


@pytest.mark.asyncio
async def test_dry_run_applies_model_extraction_to_the_paste_lane(db_session: AsyncSession) -> None:
    enriched = {
        "text": "hello",
        "_model_items": [
            {
                "content": "Prefers small diffs.",
                "bucket": "semantic",
                "importance": 0.8,
                "confidence": 0.9,
                "profile_key": None,
                "profile_value": None,
                "trigger": None,
            },
        ],
    }
    extraction = AsyncMock(return_value=enriched)

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run._with_model_extracted_paste_items",
            extraction,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.get_session",
            session_context(db_session),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.external_source_providers_configured",
            AsyncMock(return_value=False),
        ),
    ):
        response = await dry_run_import_memories(
            MemoryImportDryRunRequest(
                source="pasted_memory",
                payload={"text": "hello"},
                use_model_extraction=True,
                migration=MemoryImportMigrationOptions(target_agent_id="agent-1"),
            ),
        )

    extraction.assert_awaited_once_with({"text": "hello"}, agent_id="agent-1")
    assert response.result.summary.mapped_items == 1
    assert response.result.summary.source == "pasted_memory"
