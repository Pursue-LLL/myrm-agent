"""Memory import confirm handler.

[INPUT]
app.services.memory.operations.crud.import_flows.instruction_lane (POS: 指令/MCP/模型车道)
app.services.memory.operations.crud.import_flows.confirm_followups (POS: cron/会话/就绪车道)
app.services.memory.imports.import_sessions (POS: 记忆导入审查会话)

[OUTPUT]
confirm_import_memories: write the reviewed payload, replay the reviewed lanes in
order and report the post-import readiness verdict.

[POS]
Write half of the import lifecycle; consumes the dry-run session id and records the
ledger entries that rollback later replays.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.database.connection import get_session
from app.platform_utils.workspace_root import get_workspace_root
from app.schemas.memory.archive import (
    CronImportSummary,
    MemoryImportConfirmRequest,
    MemoryImportConfirmResponse,
    MemoryImportReadiness,
)
from app.services.memory.imports.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionError,
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_flows.confirm_followups import (
    apply_cron_lane,
    apply_session_lane,
    build_readiness,
    persist_readiness,
    resolve_migration_competitor,
    run_post_import_diagnostic,
)
from app.services.memory.operations.crud.import_flows.instruction_lane import (
    InstructionLaneOutcome,
    apply_instruction_lane,
)
from app.services.migration.source.source_secrets_importer import (
    external_source_providers_configured,
)
from app.services.migration.workspace_bind_candidates import candidates_from_metadata, to_api_candidates


async def confirm_import_memories(
    body: MemoryImportConfirmRequest,
) -> MemoryImportConfirmResponse:
    """Confirm a memory import from a server-bound dry-run session."""

    from app.services.migration.memory_import_binding import create_global_import_memory_manager

    async with get_session() as db:
        try:
            session_service = MemoryImportSessionService(db)
            metadata = await session_service.get_pending_session_metadata(body.dry_run_id)
            workspace_root: str | None = str(get_workspace_root())
            manager = await create_global_import_memory_manager()
            result = await session_service.confirm_import(
                dry_run_id=body.dry_run_id,
                manager=manager,
                skip_duplicates=body.skip_duplicates,
            )
            raw_plan = metadata.get("instruction_plan")

            lanes = InstructionLaneOutcome(result=None, mcp_imported_disabled_count=0)
            if body.apply_instructions and isinstance(raw_plan, dict):
                lanes = await apply_instruction_lane(
                    db,
                    import_batch_id=result.import_batch_id,
                    raw_plan=raw_plan,
                    raw_options=metadata.get("migration_options"),
                    metadata=metadata,
                    workspace_root=workspace_root,
                )

            target_agent_id = lanes.result.target_agent_id if lanes.result else None
            cron_import_summary: CronImportSummary | None = None
            cron_plan = metadata.get("cron_migration")
            if isinstance(cron_plan, dict):
                raw_options = metadata.get("migration_options")
                cron_import_summary = await apply_cron_lane(
                    db,
                    import_batch_id=result.import_batch_id,
                    cron_plan=cron_plan,
                    target_agent_id=target_agent_id,
                    fallback_agent_id=(
                        str(raw_options["target_agent_id"])
                        if isinstance(raw_options, dict) and raw_options.get("target_agent_id")
                        else None
                    ),
                )

            imported_session_count = 0
            imported_chat_ids: list[str] = []
            sessions = metadata.get("session_migration")
            if body.import_sessions and isinstance(sessions, list) and sessions:
                session_lane = await apply_session_lane(
                    db,
                    import_batch_id=result.import_batch_id,
                    sessions=[item for item in sessions if isinstance(item, dict)],
                    target_workspace_override=workspace_root,
                    target_agent_id=target_agent_id,
                )
                imported_session_count = session_lane.imported_count
                imported_chat_ids = session_lane.chat_ids

            diagnostic = await run_post_import_diagnostic(
                db,
                manager=manager,
                session_service=session_service,
                import_batch_id=result.import_batch_id,
            )
            result.diagnostic_status = diagnostic.status
            result.diagnostic_run_id = diagnostic.run_id

            readiness = await _finalize_readiness(
                session_service,
                metadata=metadata,
                import_batch_id=result.import_batch_id,
                diagnostic_status=diagnostic.status,
                diagnostic_failed_count=diagnostic.failed_count,
                mcp_config_count=lanes.mcp_imported_disabled_count,
                workspace_rules_skipped=lanes.result.workspace_rules_skipped if lanes.result else 0,
                target_agent_id=target_agent_id,
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
        target_agent_id=target_agent_id,
        agent_created=lanes.result.agent_created if lanes.result else False,
        global_instructions_updated=lanes.result.global_instructions_updated if lanes.result else False,
        workspace_rules_written=lanes.result.workspace_rules_written if lanes.result else 0,
        workspace_rules_skipped=lanes.result.workspace_rules_skipped if lanes.result else 0,
        readiness=readiness,
        workspace_bind_candidates=to_api_candidates(candidates_from_metadata(metadata.get("workspace_bind_candidates"))),
        cron_import_summary=cron_import_summary,
        imported_session_count=imported_session_count,
        imported_chat_ids=imported_chat_ids,
    )


async def _finalize_readiness(
    session_service: MemoryImportSessionService,
    *,
    metadata: dict[str, object],
    import_batch_id: str,
    diagnostic_status: str | None,
    diagnostic_failed_count: int,
    mcp_config_count: int,
    workspace_rules_skipped: int,
    target_agent_id: str | None,
) -> MemoryImportReadiness:
    source_has_api_keys = metadata.get("source_has_api_keys") is True
    providers_configured = await external_source_providers_configured()
    migration_competitor = resolve_migration_competitor(metadata)
    model_migration = metadata.get("model_migration")

    readiness = await build_readiness(
        providers_configured=providers_configured,
        source_has_api_keys=source_has_api_keys,
        diagnostic_status=diagnostic_status,
        diagnostic_failed_count=diagnostic_failed_count,
        mcp_config_count=mcp_config_count,
        workspace_rules_skipped=workspace_rules_skipped,
        migration_competitor=migration_competitor,
        target_agent_id=target_agent_id,
        model_migration=model_migration,
    )
    await persist_readiness(
        session_service,
        import_batch_id=import_batch_id,
        readiness=readiness,
        recheck_facts=ImportReadinessRecheckFacts(
            source_has_api_keys=source_has_api_keys,
            diagnostic_status=diagnostic_status,
            diagnostic_failed_count=diagnostic_failed_count,
            mcp_config_count=mcp_config_count,
            workspace_rules_skipped=workspace_rules_skipped,
            migration_competitor=migration_competitor,
        ),
    )
    return readiness
