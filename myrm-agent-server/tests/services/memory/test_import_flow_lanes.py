"""Regression tests for the import lane helpers and the confirm handler wiring.

The confirm handler used to inline every lane, so a single unbound local or a
reordered lane was invisible to the suite. These tests pin the pieces that are
easy to break when a lane moves: instruction-plan parsing, the episodic suffix in
the response rows, the token-economics estimate, and the confirm path where
instructions are skipped while reviewed sessions are still imported.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.schemas.memory.archive import MemoryImportConfirmRequest
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from app.services.memory.operations.crud.import_archive import (
    _COMPETITOR_AVG_SKILL_TOKENS,
    _MYRM_AVG_INDEX_TOKENS,
)
from app.services.memory.operations.crud.import_flows.confirm_flow import confirm_import_memories
from app.services.memory.operations.crud.import_flows.confirm_followups import (
    resolve_migration_competitor,
)
from app.services.memory.operations.crud.import_flows.dry_run_preview import (
    build_instruction_preview,
    build_lane_response_rows,
    build_token_economics,
    skipped_cron_preview,
)
from app.services.memory.operations.crud.import_flows.instruction_lane import (
    mcp_configs_from_metadata,
    options_from_metadata,
    plan_from_metadata,
)
from app.services.migration.source.source_migration_types import MigrationLanePreview
from tests.services.memory.test_import_sessions import _FakeMemoryManager


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _session_context(session: AsyncSession):
    @asynccontextmanager
    async def _context() -> AsyncIterator[AsyncSession]:
        yield session

    return _context


def _reviewed_session() -> dict[str, object]:
    return {
        "session_id": "session-1",
        "title": "Debug the importer",
        "source_platform": "claude_code",
        "total_tool_calls": 2,
        "turns": [
            {"role": "user", "content": "The importer drops my session.", "timestamp": 0},
            {"role": "assistant", "content": "Let me trace it.", "timestamp": 0},
        ],
    }


@pytest.mark.asyncio
async def test_confirm_still_imports_sessions_when_instructions_are_skipped(
    db_session: AsyncSession,
) -> None:
    """Skipping the instruction lane must not leave the session lane without a workspace root."""

    service = MemoryImportSessionService(db_session)
    dry_run_id, _preview, _hash, _expires = await service.create_dry_run(
        {"data": {"semantic": [{"content": "Workspace roots come from settings.", "metadata": {}}]}},
        "native_json",
        session_metadata={
            "session_migration": [_reviewed_session()],
            "source_has_api_keys": False,
        },
    )
    request = MemoryImportConfirmRequest(
        dry_run_id=dry_run_id,
        apply_instructions=False,
        import_sessions=True,
    )

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.get_session",
            _session_context(db_session),
        ),
        patch(
            "app.services.migration.memory_import_binding.create_global_import_memory_manager",
            return_value=_FakeMemoryManager(),
        ),
    ):
        response = await confirm_import_memories(request)

    assert response.total_imported == 1
    assert response.imported_session_count == 1
    assert len(response.imported_chat_ids) == 1
    assert response.target_agent_id is None
    assert response.readiness is not None


@pytest.mark.asyncio
async def test_confirm_maps_session_errors_to_http_status(db_session: AsyncSession) -> None:
    request = MemoryImportConfirmRequest(dry_run_id="memory-import:missing", apply_instructions=False)

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.get_session",
            _session_context(db_session),
        ),
        patch(
            "app.services.migration.memory_import_binding.create_global_import_memory_manager",
            return_value=_FakeMemoryManager(),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await confirm_import_memories(request)

    assert exc_info.value.status_code in {404, 409}


def test_plan_from_metadata_keeps_only_complete_rules() -> None:
    plan = plan_from_metadata(
        {
            "competitor": "hermes",
            "agent_persona": "Be terse.",
            "global_supplement": "Use metric units.",
            "workspace_rules": [
                {"filename": "AGENTS.md", "content": "Run tests."},
                {"filename": "EMPTY.md", "content": "   "},
                {"filename": "", "content": "orphan"},
                "not-a-dict",
            ],
        }
    )

    assert plan.competitor == "hermes"
    assert plan.agent_persona == "Be terse."
    assert [rule.filename for rule in plan.workspace_rules] == ["AGENTS.md"]


def test_options_from_metadata_defaults_match_the_request_schema() -> None:
    default = options_from_metadata(None)
    assert default.target_agent_id is None
    assert default.clone_from_agent_id == "builtin-general"
    assert default.include_episodic is False
    assert default.apply_global_instructions is True

    explicit = options_from_metadata(
        {
            "target_agent_id": "agent-7",
            "clone_from_agent_id": "builtin-coder",
            "include_episodic": True,
            "apply_global_instructions": False,
        }
    )
    assert explicit.target_agent_id == "agent-7"
    assert explicit.include_episodic is True
    assert explicit.apply_global_instructions is False


def test_mcp_configs_from_metadata_drops_unnamed_servers() -> None:
    assert mcp_configs_from_metadata({"mcp_configs": [{"name": "fs"}, {"name": ""}, "raw"]}) == [{"name": "fs"}]
    assert mcp_configs_from_metadata({}) == []


def test_resolve_migration_competitor_prefers_the_recorded_source() -> None:
    assert resolve_migration_competitor({"migration_competitor": " Hermes "}) == "Hermes"
    assert (
        resolve_migration_competitor({"migration_competitor": "  ", "instruction_plan": {"competitor": "OpenClaw"}}) == "openclaw"
    )
    assert resolve_migration_competitor({}) is None


def test_lane_rows_flag_excluded_episodic_only_when_the_user_opted_out() -> None:
    lanes = [
        MigrationLanePreview(lane="memory", status="ready", label="memory_lane", detail="pending"),
        MigrationLanePreview(lane="instruction", status="ready", label="instruction_lane", detail="ok"),
    ]
    excluded = build_lane_response_rows(
        lanes,
        memory_status="warning",
        memory_mapped=4,
        episodic_excluded=True,
    )
    kept = build_lane_response_rows(
        lanes,
        memory_status="warning",
        memory_mapped=4,
        episodic_excluded=False,
    )

    assert excluded[0].status == "warning"
    assert excluded[0].detail == "4 mapped item(s), episodic excluded"
    assert kept[0].detail == "4 mapped item(s)"
    assert excluded[1].detail == "ok"


def test_token_economics_uses_the_published_constants() -> None:
    assert build_token_economics(0) is None
    estimate = build_token_economics(10)
    assert estimate is not None
    assert estimate.source_tokens_per_turn == 10 * _COMPETITOR_AVG_SKILL_TOKENS
    assert estimate.myrm_tokens_per_turn == 10 * _MYRM_AVG_INDEX_TOKENS
    assert estimate.savings_percent == 94.0


def test_instruction_preview_truncates_persona_and_skips_empty_rule_names() -> None:
    persona, rule_names = build_instruction_preview(
        {
            "agent_persona": "p" * 1500,
            "workspace_rules": [{"filename": "AGENTS.md"}, {"filename": " "}, "raw"],
        }
    )

    assert persona is not None
    assert len(persona) == 1200
    assert rule_names == ["AGENTS.md"]


def test_skipped_cron_preview_is_empty_without_a_plan() -> None:
    assert skipped_cron_preview(None) == []


def _hermes_loaded_payload() -> dict[str, object]:
    from app.services.migration.hermes.hermes_cron_converter import build_hermes_cron_migration_plan

    cron_plan = build_hermes_cron_migration_plan(
        [
            {
                "id": "job-1",
                "name": "Morning brief",
                "prompt": "Summarize overnight news.",
                "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            },
            {
                "id": "job-2",
                "name": "Watchdog",
                "no_agent": True,
                "script": "/tmp/check.sh",
                "schedule": {"kind": "interval", "minutes": 30},
            },
        ]
    )
    return {
        "_source": "hermes",
        "soul_md": "Be a careful engineer.",
        "memory_md": "Prefers small diffs.\n§\nRuns pytest before every commit.",
        "cursor_rules": [{"name": "agents", "content": "Run the tests before pushing."}],
        "skills": [{"name": "review", "content": "Review code.", "path": "skills/review.md"}],
        "env_keys": ["OPENAI_API_KEY"],
        "mcp_servers": {
            "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]},
        },
        "hermes_config": {"auxiliary": {"model": "aux-model"}, "moa": {"models": ["a"]}},
        "hermes_cron_plan": cron_plan.to_metadata_dict(),
        "sessions": [_reviewed_session()],
    }


@pytest.mark.asyncio
async def test_dry_run_previews_every_competitor_lane_and_binds_metadata(
    db_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.database.models.memory import MemoryImportDryRunModel
    from app.schemas.memory.archive import MemoryImportDryRunRequest
    from app.services.memory.operations.crud.import_flows.dry_run import dry_run_import_memories

    loaded = _hermes_loaded_payload()
    request = MemoryImportDryRunRequest(payload={"competitor": "hermes", "root": "/tmp/hermes"})

    with (
        patch(
            "app.services.migration.source.source_payload_loader.load_source_payload",
            return_value=loaded,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.get_session",
            _session_context(db_session),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.external_source_providers_configured",
            return_value=True,
        ),
    ):
        response = await dry_run_import_memories(request)

    assert response.result.summary.mapped_items == 2
    assert response.pending_skills_total == 1
    assert response.instruction_preview_persona == "Be a careful engineer."
    assert response.instruction_preview_rule_names == ["imported-hermes-agents.md"]
    assert response.token_economics is not None
    assert response.token_economics.skill_count == 1
    assert [row.lane for row in response.migration_lanes] == ["instruction", "memory", "skill", "credential", "cron", "session"]
    memory_lane = next(row for row in response.migration_lanes if row.lane == "memory")
    assert memory_lane.status == "ready"
    assert memory_lane.detail == "2 mapped item(s)"
    assert [(part.code, part.params) for part in memory_lane.detail_parts] == [
        ("memory_mapped", {"count": 2}),
    ]
    instruction_lane = next(row for row in response.migration_lanes if row.lane == "instruction")
    assert [part.code for part in instruction_lane.detail_parts] == ["instruction_persona", "instruction_rules"]
    assert response.mcp_servers_preview[0]["name"] == "filesystem"
    assert [(row.name, row.reason) for row in response.cron_skipped] == [("Watchdog", "no_agent_script")]
    assert len(response.session_preview) == 1
    assert response.session_preview[0]["turn_count"] == 2
    assert response.workspace_bind_candidates == []

    row = (
        await db_session.execute(select(MemoryImportDryRunModel).where(MemoryImportDryRunModel.id == response.dry_run_id))
    ).scalar_one()
    metadata = row.metadata_json or {}
    assert metadata["migration_competitor"] == "hermes"
    assert metadata["source_has_api_keys"] is True
    assert metadata["providers_configured"] is True
    assert metadata["instruction_plan"]["mcp_configs"][0]["name"] == "filesystem"
    assert metadata["model_migration"]["hermes_moa"] == {"models": ["a"]}
    assert metadata["cron_migration"]["importable"][0]["name"] == "Morning brief"
    assert metadata["session_migration"][0]["session_id"] == "session-1"
    assert metadata["migration_options"]["clone_from_agent_id"] == "builtin-general"


@pytest.mark.asyncio
async def test_dry_run_native_payload_skips_competitor_introspection(db_session: AsyncSession) -> None:
    from app.schemas.memory.archive import MemoryImportDryRunRequest
    from app.services.memory.operations.crud.import_flows.dry_run import dry_run_import_memories

    request = MemoryImportDryRunRequest(
        payload={"data": {"semantic": [{"content": "Native exports still preview.", "metadata": {}}]}},
    )

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.get_session",
            _session_context(db_session),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.dry_run.external_source_providers_configured",
            return_value=False,
        ),
    ):
        response = await dry_run_import_memories(request)

    assert response.result.summary.mapped_items == 1
    assert response.migration_lanes == []
    assert response.token_economics is None
    assert response.instruction_preview_persona is None
    assert response.mcp_servers_preview == []
    assert response.cron_skipped == []
    assert response.workspace_bind_candidates == []
    assert response.providers_configured is False


@pytest.mark.asyncio
async def test_diagnostic_failure_is_recorded_instead_of_raised(db_session: AsyncSession) -> None:
    from app.services.memory.operations.crud.import_flows.confirm_followups import DiagnosticOutcome, run_post_import_diagnostic

    saved: list[dict[str, object]] = []

    class _RecordingSessionService:
        async def save_post_import_diagnostic(self, **kwargs: object) -> None:
            saved.append(kwargs)

    with patch(
        "app.services.memory.command_center.command_center.MemoryCommandCenterService",
        side_effect=RuntimeError("snapshot failed"),
    ):
        outcome = await run_post_import_diagnostic(
            db_session,
            manager=_FakeMemoryManager(),
            session_service=_RecordingSessionService(),  # type: ignore[arg-type]
            import_batch_id="memory-import-batch:test",
        )

    assert outcome == DiagnosticOutcome(status="failed", run_id=None, failed_count=1)
    assert saved[-1]["diagnostic_run_id"] == "post-import-diagnostic:failed"
    assert saved[-1]["failed_count"] == 1


@pytest.mark.asyncio
async def test_readiness_persistence_failure_does_not_raise() -> None:
    from app.services.memory.imports.import_sessions import ImportReadinessRecheckFacts
    from app.services.memory.imports.readiness import build_import_readiness
    from app.services.memory.operations.crud.import_flows.confirm_followups import persist_readiness

    class _FailingSessionService:
        async def save_post_import_readiness(self, **kwargs: object) -> None:
            raise RuntimeError("database is locked")

    readiness = build_import_readiness(
        providers_configured=True,
        source_has_api_keys=False,
        diagnostic_status="passed",
        diagnostic_failed_count=0,
        mcp_config_count=0,
        workspace_rules_skipped=0,
        migration_competitor=None,
        moa_overlay_configured=None,
    )
    await persist_readiness(
        _FailingSessionService(),  # type: ignore[arg-type]
        import_batch_id="memory-import-batch:test",
        readiness=readiness,
        recheck_facts=ImportReadinessRecheckFacts(
            source_has_api_keys=False,
            diagnostic_status="passed",
            diagnostic_failed_count=0,
            mcp_config_count=0,
            workspace_rules_skipped=0,
        ),
    )


def test_lane_response_rows_mark_excluded_episodic_as_a_part() -> None:
    from app.services.memory.operations.crud.import_flows.dry_run_preview import build_lane_response_rows
    from app.services.migration.source.source_migration_types import LaneDetailPart, MigrationLanePreview

    lane = MigrationLanePreview(
        lane="memory",
        status="pending",
        label="memory_lane",
        detail="0 mapped item(s)",
        detail_parts=(LaneDetailPart("memory_mapped", {"count": 0}),),
    )

    rows = build_lane_response_rows(
        [lane],
        memory_status="ready",
        memory_mapped=3,
        episodic_excluded=True,
    )

    assert rows[0].status == "ready"
    assert [(part.code, part.params) for part in rows[0].detail_parts] == [
        ("memory_mapped", {"count": 3}),
        ("memory_episodic_excluded", {}),
    ]
