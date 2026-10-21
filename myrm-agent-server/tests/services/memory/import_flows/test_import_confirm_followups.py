"""Coverage for the instruction, cron, diagnostic and readiness follow-up lanes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.archive import (
    CronImportSummary,
    MemoryImportConfirmRequest,
    MemoryImportReadiness,
)
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from app.services.memory.operations.crud.import_flows.confirm_flow import confirm_import_memories
from app.services.memory.operations.crud.import_flows.confirm_followups import (
    DiagnosticOutcome,
    apply_cron_lane,
    build_readiness,
    run_post_import_diagnostic,
)
from app.services.memory.operations.crud.import_flows.instruction_lane import (
    InstructionLaneOutcome,
    apply_instruction_lane,
)
from app.services.migration.hermes.hermes_cron_migration import HermesCronApplyResult
from app.services.migration.source.source_migration_types import InstructionApplyResult
from tests.services.memory.import_flows.support import session_context
from tests.services.memory.test_import_sessions import _FakeMemoryManager


@pytest.mark.asyncio
async def test_instruction_lane_records_rollback_and_model_side_effects(db_session: AsyncSession) -> None:
    applied = InstructionApplyResult(
        target_agent_id="agent-1",
        agent_created=False,
        global_instructions_updated=True,
        workspace_rules_written=1,
    )
    merge = AsyncMock()
    model_migration = AsyncMock()

    with (
        patch(
            "app.services.migration.instruction_writer.apply_instruction_plan",
            AsyncMock(return_value=applied),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.side_effects._write_migrated_mcp_configs",
            AsyncMock(side_effect=RuntimeError("cannot write mcp")),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.side_effects._apply_model_migration",
            model_migration,
        ),
        patch(
            "app.services.memory.imports.import_ledger.MemoryImportLedgerService.merge_batch_metadata",
            merge,
        ),
    ):
        outcome = await apply_instruction_lane(
            db_session,
            import_batch_id="memory-import-batch:test",
            raw_plan={
                "competitor": "hermes",
                "agent_persona": "Be terse.",
                "workspace_rules": [{"filename": "AGENTS.md", "content": "Run tests."}],
                "mcp_configs": [{"name": "fs"}],
            },
            raw_options={"apply_global_instructions": True},
            metadata={"model_migration": {"hermes_auxiliary": {"x": "y"}}},
            workspace_root="/tmp",
        )

    assert outcome.result is applied
    assert outcome.mcp_imported_disabled_count == 0
    merge.assert_awaited_once()
    assert "instruction_rollback" in merge.await_args.args[1]
    model_migration.assert_awaited_once_with(
        {"hermes_auxiliary": {"x": "y"}},
        target_agent_id="agent-1",
    )


@pytest.mark.asyncio
async def test_cron_lane_summarizes_imported_and_skipped_jobs(db_session: AsyncSession) -> None:
    apply = AsyncMock(return_value=HermesCronApplyResult(created_job_ids=("job-1",), failed_count=0))
    merge = AsyncMock()
    plan = {
        "importable": [
            {
                "name": "Morning brief",
                "job_type": "agent",
                "schedule_kind": "cron",
                "schedule_expr": "0 9 * * *",
                "prompt": "Summarize.",
            },
        ],
        "skipped": [{"name": "Watchdog", "reason": "no_agent_script"}],
    }

    with (
        patch("app.services.migration.hermes.hermes_cron_migration.apply_hermes_cron_migration_plan", apply),
        patch(
            "app.services.memory.imports.import_ledger.MemoryImportLedgerService.merge_batch_metadata",
            merge,
        ),
    ):
        summary = await apply_cron_lane(
            db_session,
            import_batch_id="memory-import-batch:test",
            cron_plan=plan,
            target_agent_id="agent-1",
            fallback_agent_id=None,
        )

    assert summary.imported_count == 1
    assert summary.failed_count == 0
    assert summary.skipped_count == 1
    apply.assert_awaited_once()
    merge.assert_awaited_once()

    with (
        patch(
            "app.services.migration.hermes.hermes_cron_migration.apply_hermes_cron_migration_plan",
            AsyncMock(return_value=HermesCronApplyResult(created_job_ids=(), failed_count=0)),
        ),
        patch(
            "app.services.memory.imports.import_ledger.MemoryImportLedgerService.merge_batch_metadata",
            merge,
        ),
    ):
        empty = await apply_cron_lane(
            db_session,
            import_batch_id="memory-import-batch:test",
            cron_plan={"importable": [], "skipped": []},
            target_agent_id=None,
            fallback_agent_id="agent-fallback",
        )

    assert empty.imported_count == 0
    assert merge.await_count == 1


@pytest.mark.asyncio
async def test_confirm_wires_instruction_and_cron_lanes(db_session: AsyncSession) -> None:
    service = MemoryImportSessionService(db_session)
    dry_run_id, _preview, _hash, _expires = await service.create_dry_run(
        {"data": {"semantic": [{"content": "Confirm replays reviewed lanes.", "metadata": {}}]}},
        "native_json",
        session_metadata={
            "instruction_plan": {
                "competitor": "claude_code",
                "agent_persona": "Be terse.",
                "workspace_rules": [{"filename": "AGENTS.md", "content": "Run tests."}],
                "mcp_configs": [{"name": "fs"}],
            },
            "migration_options": {"target_agent_id": "agent-1", "apply_global_instructions": True},
            "cron_migration": {"importable": [], "skipped": []},
        },
    )
    applied = InstructionApplyResult(
        target_agent_id="agent-1",
        agent_created=False,
        global_instructions_updated=True,
        workspace_rules_written=1,
    )
    instruction_lane = AsyncMock(
        return_value=InstructionLaneOutcome(result=applied, mcp_imported_disabled_count=1),
    )
    cron_lane = AsyncMock(
        return_value=CronImportSummary(imported_count=1, failed_count=0, skipped_count=0),
    )
    readiness = MemoryImportReadiness(status="ready")

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.get_session",
            session_context(db_session),
        ),
        patch(
            "app.services.migration.memory_import_binding.create_global_import_memory_manager",
            return_value=_FakeMemoryManager(),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.apply_instruction_lane",
            instruction_lane,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.apply_cron_lane",
            cron_lane,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.run_post_import_diagnostic",
            AsyncMock(return_value=DiagnosticOutcome(status="passed", run_id="diagnostic-1", failed_count=0)),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.build_readiness",
            AsyncMock(return_value=readiness),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.persist_readiness",
            AsyncMock(),
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_flow.external_source_providers_configured",
            AsyncMock(return_value=False),
        ),
    ):
        response = await confirm_import_memories(
            MemoryImportConfirmRequest(
                dry_run_id=dry_run_id,
                apply_instructions=True,
                import_sessions=False,
            ),
        )

    assert response.target_agent_id == "agent-1"
    assert response.global_instructions_updated is True
    assert response.workspace_rules_written == 1
    assert response.cron_import_summary is not None
    assert response.cron_import_summary.imported_count == 1
    assert response.readiness is readiness
    assert instruction_lane.await_args.kwargs["raw_plan"]["competitor"] == "claude_code"
    assert cron_lane.await_args.kwargs["target_agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_post_import_diagnostic_records_the_snapshot(db_session: AsyncSession) -> None:
    snapshot = SimpleNamespace(health=SimpleNamespace(cache_status="ok"), runtime=object())
    diagnostic = SimpleNamespace(id="diagnostic-1", status="passed", failed_count=0)
    session_service = SimpleNamespace(save_post_import_diagnostic=AsyncMock())

    with (
        patch(
            "app.services.memory.command_center.command_center.MemoryCommandCenterService.build_snapshot",
            AsyncMock(return_value=snapshot),
        ),
        patch(
            "app.services.memory.diagnostics.diagnostics.MemoryDiagnosticsService.run_diagnostics",
            AsyncMock(return_value=diagnostic),
        ),
    ):
        outcome = await run_post_import_diagnostic(
            db_session,
            manager=_FakeMemoryManager(),  # type: ignore[arg-type]
            session_service=session_service,  # type: ignore[arg-type]
            import_batch_id="memory-import-batch:test",
        )

    assert outcome == DiagnosticOutcome(status="passed", run_id="diagnostic-1", failed_count=0)
    session_service.save_post_import_diagnostic.assert_awaited_once_with(
        import_batch_id="memory-import-batch:test",
        diagnostic_run_id="diagnostic-1",
        diagnostic_status="passed",
        failed_count=0,
    )


@pytest.mark.asyncio
async def test_post_import_diagnostic_survives_a_persistence_failure(db_session: AsyncSession) -> None:
    session_service = SimpleNamespace(
        save_post_import_diagnostic=AsyncMock(side_effect=RuntimeError("ledger locked")),
    )

    with patch(
        "app.services.memory.command_center.command_center.MemoryCommandCenterService.build_snapshot",
        AsyncMock(side_effect=RuntimeError("store unavailable")),
    ):
        outcome = await run_post_import_diagnostic(
            db_session,
            manager=_FakeMemoryManager(),  # type: ignore[arg-type]
            session_service=session_service,  # type: ignore[arg-type]
            import_batch_id="memory-import-batch:test",
        )

    assert outcome == DiagnosticOutcome(status="failed", run_id=None, failed_count=1)


@pytest.mark.asyncio
async def test_build_readiness_resolves_the_hermes_moa_overlay() -> None:
    readiness = MemoryImportReadiness(status="ready")
    resolve_overlay = AsyncMock(return_value=True)
    build = Mock(return_value=readiness)

    with (
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_followups._resolve_post_import_moa_overlay_configured",
            resolve_overlay,
        ),
        patch(
            "app.services.memory.operations.crud.import_flows.confirm_followups.build_import_readiness",
            build,
        ),
    ):
        result = await build_readiness(
            providers_configured=True,
            source_has_api_keys=True,
            diagnostic_status="passed",
            diagnostic_failed_count=0,
            mcp_config_count=0,
            workspace_rules_skipped=0,
            migration_competitor="hermes",
            target_agent_id="agent-1",
            model_migration={"hermes_moa": {"models": ["a"]}},
        )

    assert result is readiness
    resolve_overlay.assert_awaited_once_with("agent-1", {"hermes_moa": {"models": ["a"]}})
    assert build.call_args.kwargs["moa_overlay_configured"] is True
