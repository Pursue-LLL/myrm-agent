"""Memory import confirm and readiness handlers.

[INPUT]
app.services.memory.imports.import_sessions::MemoryImportSessionService (POS: 记忆导入审查会话)

[OUTPUT]
confirm_import_memories: write the reviewed payload, attach MCP/model/workspace
side effects and report post-import readiness.

[POS]
Write half of the import lifecycle; consumes the dry-run session id and records
the transaction ledger entry that rollback later replays.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.database.connection import get_session
from app.schemas.memory.archive import (
    CronImportSummary,
    MemoryImportConfirmRequest,
    MemoryImportConfirmResponse,
    MemoryImportReadiness,
    WorkspaceBindCandidate,
)
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
from app.services.memory.imports.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionError,
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_readiness import build_import_readiness
from app.services.memory.operations.crud.import_side_effects import (
    _apply_model_migration,
    _resolve_post_import_moa_overlay_configured,
    _write_migrated_mcp_configs,
)
from app.services.migration.source.source_secrets_importer import (
    external_source_providers_configured,
)

logger = logging.getLogger(__name__)


async def confirm_import_memories(
    body: MemoryImportConfirmRequest,
) -> MemoryImportConfirmResponse:
    """Confirm a memory import from a server-bound dry-run session."""

    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.migration.instruction_writer import (
        apply_instruction_plan,
        instruction_rollback_record_from_apply,
        instruction_rollback_record_to_metadata,
    )
    from app.services.migration.memory_import_binding import (
        create_global_import_memory_manager,
    )
    from app.services.migration.source.source_migration_types import (
        MigrationWizardOptions,
        SourceInstructionPlan,
        WorkspaceRuleWrite,
    )

    instruction_result = None
    readiness: MemoryImportReadiness | None = None
    workspace_bind_candidates: list[WorkspaceBindCandidate] = []
    cron_import_summary: CronImportSummary | None = None
    async with get_session() as db:
        try:
            session_service = MemoryImportSessionService(db)
            metadata = await session_service.get_pending_session_metadata(body.dry_run_id)
            from app.services.migration.workspace_bind_candidates import (
                candidates_from_metadata,
            )

            workspace_bind_candidates = [
                WorkspaceBindCandidate(
                    path=item.path,
                    label=item.label,
                    has_obsidian_config=item.has_obsidian_config,
                    markdown_file_count=item.markdown_file_count,
                )
                for item in candidates_from_metadata(metadata.get("workspace_bind_candidates"))
            ]
            source_has_api_keys_raw = metadata.get("source_has_api_keys")
            source_has_api_keys = source_has_api_keys_raw is True
            mcp_imported_disabled_count = 0
            raw_instruction_plan = metadata.get("instruction_plan")
            diagnostic_failed_count = 0

            manager = await create_global_import_memory_manager()
            result = await session_service.confirm_import(
                dry_run_id=body.dry_run_id,
                manager=manager,
                skip_duplicates=body.skip_duplicates,
            )

            if body.apply_instructions and isinstance(raw_instruction_plan, dict):
                raw_plan = raw_instruction_plan
                raw_opts = metadata.get("migration_options")
                opts = MigrationWizardOptions(
                    target_agent_id=(
                        str(raw_opts["target_agent_id"])
                        if isinstance(raw_opts, dict) and raw_opts.get("target_agent_id")
                        else None
                    ),
                    clone_from_agent_id=(
                        str(raw_opts.get("clone_from_agent_id", "builtin-general"))
                        if isinstance(raw_opts, dict)
                        else "builtin-general"
                    ),
                    include_episodic=(bool(raw_opts.get("include_episodic")) if isinstance(raw_opts, dict) else False),
                    apply_global_instructions=(
                        bool(raw_opts.get("apply_global_instructions", True)) if isinstance(raw_opts, dict) else True
                    ),
                )
                rules_raw = raw_plan.get("workspace_rules")
                workspace_rules: list[WorkspaceRuleWrite] = []
                if isinstance(rules_raw, list):
                    for item in rules_raw:
                        if isinstance(item, dict):
                            filename = str(item.get("filename", "")).strip()
                            content = str(item.get("content", "")).strip()
                            if filename and content:
                                workspace_rules.append(
                                    WorkspaceRuleWrite(filename=filename, content=content),
                                )
                mcp_configs_raw = raw_plan.get("mcp_configs")
                mcp_configs_to_write: list[dict[str, object]] = []
                if isinstance(mcp_configs_raw, list):
                    mcp_configs_to_write = [item for item in mcp_configs_raw if isinstance(item, dict) and item.get("name")]

                plan = SourceInstructionPlan(
                    competitor=str(raw_plan.get("competitor", "unknown")),
                    agent_persona=str(raw_plan.get("agent_persona", "")),
                    global_supplement=str(raw_plan.get("global_supplement", "")),
                    workspace_rules=workspace_rules,
                )
                from app.platform_utils.workspace_root import get_workspace_root

                workspace_root = str(get_workspace_root()) or None
                instruction_result = await apply_instruction_plan(
                    plan,
                    opts,
                    workspace_root=workspace_root,
                )

                if mcp_configs_to_write:
                    try:
                        mcp_imported_disabled_count = await _write_migrated_mcp_configs(mcp_configs_to_write)
                    except Exception as mcp_exc:
                        logger.warning("MCP config migration write failed (non-fatal): %s", mcp_exc)

                model_migration_data = metadata.get("model_migration")
                if isinstance(model_migration_data, dict):
                    moa_target_agent_id = instruction_result.target_agent_id if instruction_result else None
                    await _apply_model_migration(
                        model_migration_data,
                        target_agent_id=moa_target_agent_id,
                    )

                rollback_record = instruction_rollback_record_from_apply(
                    instruction_result,
                    competitor=plan.competitor,
                )
                await MemoryImportLedgerService(db).merge_batch_metadata(
                    result.import_batch_id,
                    {
                        "instruction_rollback": instruction_rollback_record_to_metadata(
                            rollback_record,
                        ),
                    },
                )

            cron_migration_raw = metadata.get("cron_migration")
            if isinstance(cron_migration_raw, dict):
                from app.services.migration.hermes.hermes_cron_converter import (
                    HermesCronMigrationPlan,
                )
                from app.services.migration.hermes.hermes_cron_migration import (
                    apply_hermes_cron_migration_plan,
                )

                cron_plan = HermesCronMigrationPlan.from_metadata_dict(cron_migration_raw)
                migration_opts_raw = metadata.get("migration_options")
                cron_agent_id: str | None = None
                if instruction_result and instruction_result.target_agent_id:
                    cron_agent_id = instruction_result.target_agent_id
                elif isinstance(migration_opts_raw, dict) and migration_opts_raw.get("target_agent_id"):
                    cron_agent_id = str(migration_opts_raw["target_agent_id"])
                cron_apply_result = await apply_hermes_cron_migration_plan(
                    cron_plan,
                    agent_id=cron_agent_id,
                )
                cron_import_summary = CronImportSummary(
                    imported_count=len(cron_apply_result.created_job_ids),
                    failed_count=cron_apply_result.failed_count,
                    skipped_count=len(cron_plan.skipped),
                )
                if cron_apply_result.created_job_ids or cron_apply_result.failed_count:
                    await MemoryImportLedgerService(db).merge_batch_metadata(
                        result.import_batch_id,
                        {"cron_rollback": cron_apply_result.to_metadata_dict()},
                    )

            imported_session_count = 0
            imported_chat_ids: list[str] = []
            session_migration_data = metadata.get("session_migration")
            if body.import_sessions and isinstance(session_migration_data, list) and session_migration_data:
                from app.services.migration.session_lane import SessionMigrationService

                target_agent_id = instruction_result.target_agent_id if instruction_result else None
                session_service_lane = SessionMigrationService(db)
                session_res = await session_service_lane.confirm_sessions(
                    sessions=session_migration_data,
                    target_workspace_override=workspace_root,
                    target_agent_id=target_agent_id,
                )
                imported_session_count = session_res.imported_count
                imported_chat_ids = session_res.created_chat_ids
                if imported_chat_ids:
                    await MemoryImportLedgerService(db).merge_batch_metadata(
                        result.import_batch_id,
                        {"session_rollback": {"created_chat_ids": imported_chat_ids}},
                    )

            try:
                snapshot = await MemoryCommandCenterService(db, manager).build_snapshot()
                diagnostic_run = await MemoryDiagnosticsService(db, manager).run_diagnostics(
                    health_cache_status=snapshot.health.cache_status,
                    runtime=snapshot.runtime,
                )
                await session_service.save_post_import_diagnostic(
                    import_batch_id=result.import_batch_id,
                    diagnostic_run_id=diagnostic_run.id,
                    diagnostic_status=diagnostic_run.status,
                    failed_count=diagnostic_run.failed_count,
                )
                result.diagnostic_status = diagnostic_run.status
                result.diagnostic_run_id = diagnostic_run.id
                diagnostic_failed_count = diagnostic_run.failed_count
            except Exception as exc:
                logger.warning(
                    "Post-import diagnostics failed for %s: %s",
                    result.import_batch_id,
                    exc,
                )
                result.diagnostic_status = "failed"
                diagnostic_failed_count = 1
                try:
                    await session_service.save_post_import_diagnostic(
                        import_batch_id=result.import_batch_id,
                        diagnostic_run_id="post-import-diagnostic:failed",
                        diagnostic_status="failed",
                        failed_count=1,
                    )
                except Exception as save_exc:
                    logger.warning(
                        "Post-import diagnostic failure state was not persisted: %s",
                        save_exc,
                    )
            workspace_rules_skipped_count = instruction_result.workspace_rules_skipped if instruction_result else 0
            providers_configured = await external_source_providers_configured()
            migration_competitor_raw = metadata.get("migration_competitor")
            migration_competitor = (
                migration_competitor_raw.strip()
                if isinstance(migration_competitor_raw, str) and migration_competitor_raw.strip()
                else None
            )
            if migration_competitor is None and isinstance(raw_instruction_plan, dict):
                migration_competitor = str(raw_instruction_plan.get("competitor", "")).strip().lower() or None
            moa_overlay_configured: bool | None = None
            if migration_competitor == "hermes":
                moa_overlay_configured = await _resolve_post_import_moa_overlay_configured(
                    (instruction_result.target_agent_id if instruction_result else None),
                    metadata.get("model_migration"),
                )
            readiness = build_import_readiness(
                providers_configured=providers_configured,
                source_has_api_keys=source_has_api_keys,
                diagnostic_status=result.diagnostic_status,
                diagnostic_failed_count=diagnostic_failed_count,
                mcp_config_count=mcp_imported_disabled_count,
                workspace_rules_skipped=workspace_rules_skipped_count,
                migration_competitor=migration_competitor,
                moa_overlay_configured=moa_overlay_configured,
            )
            try:
                await session_service.save_post_import_readiness(
                    import_batch_id=result.import_batch_id,
                    readiness_status=readiness.status,
                    readiness_issues=[issue.model_dump(mode="json") for issue in readiness.issues],
                    recheck_facts=ImportReadinessRecheckFacts(
                        source_has_api_keys=source_has_api_keys,
                        diagnostic_status=result.diagnostic_status,
                        diagnostic_failed_count=diagnostic_failed_count,
                        mcp_config_count=mcp_imported_disabled_count,
                        workspace_rules_skipped=workspace_rules_skipped_count,
                        migration_competitor=migration_competitor,
                    ),
                )
            except Exception as readiness_exc:
                logger.warning(
                    "Post-import readiness state was not persisted for %s: %s",
                    result.import_batch_id,
                    readiness_exc,
                )
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryImportConfirmResponse(
        imported=result.imported,
        total_imported=result.total_imported,
        import_batch_id=result.import_batch_id,
        payload_hash=result.payload_hash,
        source=result.source,
        transaction_items=len(result.transaction_items),
        diagnostic_status=result.diagnostic_status,
        diagnostic_run_id=result.diagnostic_run_id,
        target_agent_id=(instruction_result.target_agent_id if instruction_result else None),
        agent_created=instruction_result.agent_created if instruction_result else False,
        global_instructions_updated=(instruction_result.global_instructions_updated if instruction_result else False),
        workspace_rules_written=(instruction_result.workspace_rules_written if instruction_result else 0),
        workspace_rules_skipped=(instruction_result.workspace_rules_skipped if instruction_result else 0),
        readiness=readiness,
        workspace_bind_candidates=workspace_bind_candidates,
        cron_import_summary=cron_import_summary,
        imported_session_count=imported_session_count,
        imported_chat_ids=imported_chat_ids,
    )
