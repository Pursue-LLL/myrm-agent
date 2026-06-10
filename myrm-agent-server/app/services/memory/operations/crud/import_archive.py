"""Memory CRUD — import archive.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::UpdateMemoryStatusRequest (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::TasteSummaryResponse (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.archive::*Import* / *Archive* (POS: 记忆归档与导入 API Schema 层)
app.services.migration.competitor_payload_split (POS: 竞品 payload 指令/记忆车道拆分)
app.services.migration.instruction_writer (POS: 竞品指令车道写入 Agent 与全局设置)
app.services.migration.memory_import_binding (POS: 迁移事实记忆的全局 namespace 绑定)

[OUTPUT]
memory CRUD handler functions、状态变更、偏好摘要、偏好管理、服务端绑定导入、Memory Archive、导入后诊断和回滚预演端点

[POS]
记忆 API 操作层。提供标准记忆增删改查、偏好稳定性管理、单用户 archive 导出/校验，
以及 dry-run -> confirm -> diagnostic -> rollback preview -> rollback 的可审计导入流程。
"""

from __future__ import annotations

import io
import logging
import tempfile
import zipfile

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus

from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryArchiveDryRunRequest,
    MemoryArchiveDryRunResponse,
    MemoryArchiveExportResponse,
    MemoryImportConfirmRequest,
    MemoryImportConfirmResponse,
    MemoryImportDryRunRequest,
    MemoryImportDryRunResponse,
    MemoryImportRequest,
    MemoryImportResponse,
    MemoryImportRollbackPreviewResponse,
    MemoryImportRollbackRequest,
    MemoryImportRollbackResponse,
    MigrationLanePreviewItem,
)
from app.schemas.memory.crud import (
    MEMORY_EXPORT_VERSION,
    MemoryExportResponse,
)
from app.services.memory.archive import MemoryArchiveService
from app.services.memory.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics import MemoryDiagnosticsService
from app.services.memory.import_sessions import MemoryImportSessionError, MemoryImportSessionService
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _record_memory_event

logger = logging.getLogger(__name__)


async def export_memories(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryExportResponse:
    """Export all user memories as portable JSON (excludes embeddings)."""
    raw_export = await manager.export_all()
    data: dict[str, list[dict[str, object]]] = {}
    if isinstance(raw_export, dict):
        for k, entries in raw_export.items():
            key = str(k)
            if not isinstance(entries, list):
                data[key] = []
                continue
            rows: list[dict[str, object]] = []
            for item in entries:
                if isinstance(item, dict):
                    rows.append({str(ik): iv for ik, iv in item.items()})
            data[key] = rows
    total = sum(len(entries) for entries in data.values())
    return MemoryExportResponse(version=MEMORY_EXPORT_VERSION, data=data, total_count=total)


async def export_memories_markdown(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
) -> StreamingResponse:
    """Export all memories as a ZIP of Markdown files with YAML frontmatter."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        counts = await manager.export_markdown(tmp_dir, agent_id=agent_id)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            from pathlib import Path

            root = Path(tmp_dir)
            for file_path in root.rglob("*.md"):
                arcname = str(file_path.relative_to(root))
                zf.write(file_path, arcname)

        buf.seek(0)
        total = sum(counts.values())
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="memories_markdown_{total}.zip"',
                "X-Export-Count": str(total),
            },
        )


async def export_memory_archive(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryArchiveExportResponse:
    """Export the single-user memory surface as a GUI-reviewable archive."""

    async with get_session() as db:
        archive = await MemoryArchiveService(db).export_archive(manager)
    await _record_memory_event(
        kind=MemoryOperationKind.OBSERVE,
        status=MemoryOperationStatus.SUCCESS,
        summary="Memory archive exported.",
        metadata={
            "archive_version": archive.manifest.version,
            "section_count": len(archive.manifest.sections),
            "content_redacted": archive.manifest.content_redacted,
        },
    )
    return MemoryArchiveExportResponse(archive=archive)


async def dry_run_memory_archive(
    body: MemoryArchiveDryRunRequest,
) -> MemoryArchiveDryRunResponse:
    """Validate a Myrm memory archive before any restore/import work."""

    async with get_session() as db:
        result = MemoryArchiveService(db).dry_run_archive(body.archive)
    return MemoryArchiveDryRunResponse(result=result)


async def import_memories(
    _body: MemoryImportRequest,
) -> MemoryImportResponse:
    """Reject direct imports that bypass the server-bound review session."""

    raise HTTPException(
        status_code=400,
        detail="Direct memory import is disabled. Use /memory/import/dry-run and /memory/import/confirm.",
    )


async def dry_run_import_memories(body: MemoryImportDryRunRequest) -> MemoryImportDryRunResponse:
    """Preview memory import mapping and bind the review result server-side."""

    from app.services.memory.import_adapters import resolve_competitor_import_source
    from app.services.migration.competitor_migration_types import (
        CompetitorMigrationOptions,
        build_lane_previews,
        instruction_char_total,
    )
    from app.services.migration.competitor_payload_loader import (
        build_coverage_items,
        extract_pending_skills,
        is_competitor_discovery_payload,
        load_competitor_payload,
    )
    from app.services.migration.competitor_payload_split import (
        build_instruction_plan,
        extract_memory_payload,
        has_api_keys,
    )
    from app.services.migration.competitor_secrets_importer import competitor_providers_configured

    pending_skills: list[dict[str, object]] = []
    coverage_items: list[dict[str, str]] = []
    migration_lanes: list[MigrationLanePreviewItem] = []
    import_payload = body.payload
    session_metadata: dict[str, object] = {}
    resolved_source = body.source
    lane_previews = []
    is_competitor = is_competitor_discovery_payload(body.payload)
    instruction_total_chars = 0
    providers_configured = True

    if is_competitor:
        loaded_payload = load_competitor_payload(body.payload)
        pending_skills = extract_pending_skills(loaded_payload)
        coverage_items = build_coverage_items(loaded_payload)

        migration_opts = (
            CompetitorMigrationOptions(
                target_agent_id=body.migration.target_agent_id,
                clone_from_agent_id=body.migration.clone_from_agent_id,
                include_episodic=body.migration.include_episodic,
                apply_global_instructions=body.migration.apply_global_instructions,
            )
            if body.migration is not None
            else CompetitorMigrationOptions()
        )
        instruction_plan = build_instruction_plan(loaded_payload)
        import_payload = extract_memory_payload(
            loaded_payload,
            include_episodic=migration_opts.include_episodic,
        )
        competitor = str(loaded_payload.get("_source", "")).strip().lower()
        resolved_source = resolve_competitor_import_source(competitor)
        session_metadata = {
            "migration_options": {
                "target_agent_id": migration_opts.target_agent_id,
                "clone_from_agent_id": migration_opts.clone_from_agent_id,
                "include_episodic": migration_opts.include_episodic,
                "apply_global_instructions": migration_opts.apply_global_instructions,
            },
            "instruction_plan": {
                "competitor": instruction_plan.competitor,
                "agent_persona": instruction_plan.agent_persona,
                "global_supplement": instruction_plan.global_supplement,
                "workspace_rules": [
                    {"filename": rule.filename, "content": rule.content} for rule in instruction_plan.workspace_rules
                ],
            },
        }
        instruction_total_chars = instruction_char_total(instruction_plan)
        providers_configured = await competitor_providers_configured()
        lane_previews = build_lane_previews(
            instruction=instruction_plan,
            memory_mapped=0,
            memory_status="pending",
            skill_count=len(pending_skills),
            has_api_keys=has_api_keys(loaded_payload),
            providers_ready=providers_configured,
            include_episodic=migration_opts.include_episodic,
        )

    async with get_session() as db:
        dry_run_id, result, payload_hash, expires_at = await MemoryImportSessionService(db).create_dry_run(
            import_payload,
            resolved_source,
            skip_duplicates=body.skip_duplicates,
            session_metadata=session_metadata,
        )

    if is_competitor:
        migration_lanes = [
            MigrationLanePreviewItem(
                lane=lane.lane,
                status=(result.summary.status if lane.lane == "memory" else lane.status),
                label=lane.label,
                detail=(
                    f"{result.summary.mapped_items} mapped item(s)"
                    + (", episodic excluded" if body.migration is not None and not body.migration.include_episodic else "")
                    if lane.lane == "memory"
                    else lane.detail
                ),
            )
            for lane in lane_previews
        ]

    instruction_preview_persona: str | None = None
    instruction_preview_rule_names: list[str] = []
    if is_competitor and isinstance(session_metadata.get("instruction_plan"), dict):
        raw_plan = session_metadata["instruction_plan"]
        persona_raw = str(raw_plan.get("agent_persona", "")).strip()
        if persona_raw:
            instruction_preview_persona = persona_raw[:1200]
        rules_raw = raw_plan.get("workspace_rules")
        if isinstance(rules_raw, list):
            for item in rules_raw:
                if isinstance(item, dict):
                    name = str(item.get("filename", "")).strip()
                    if name:
                        instruction_preview_rule_names.append(name)

    return MemoryImportDryRunResponse(
        dry_run_id=dry_run_id,
        payload_hash=payload_hash,
        expires_at=expires_at,
        result=result,
        pending_skills=pending_skills,
        coverage_items=coverage_items,
        migration_lanes=migration_lanes,
        instruction_preview_persona=instruction_preview_persona,
        instruction_preview_rule_names=instruction_preview_rule_names,
        instruction_total_chars=instruction_total_chars if is_competitor else 0,
        providers_configured=providers_configured if is_competitor else True,
    )


async def confirm_import_memories(
    body: MemoryImportConfirmRequest,
) -> MemoryImportConfirmResponse:
    """Confirm a memory import from a server-bound dry-run session."""

    from app.services.memory.import_ledger import MemoryImportLedgerService
    from app.services.migration.competitor_migration_types import (
        CompetitorInstructionPlan,
        CompetitorMigrationOptions,
        WorkspaceRuleWrite,
    )
    from app.services.migration.instruction_writer import (
        apply_instruction_plan,
        instruction_rollback_record_from_apply,
        instruction_rollback_record_to_metadata,
    )
    from app.services.migration.memory_import_binding import create_global_import_memory_manager

    instruction_result = None
    async with get_session() as db:
        try:
            session_service = MemoryImportSessionService(db)
            metadata = await session_service.get_pending_session_metadata(body.dry_run_id)

            manager = await create_global_import_memory_manager()
            result = await session_service.confirm_import(
                dry_run_id=body.dry_run_id,
                manager=manager,
                skip_duplicates=body.skip_duplicates,
            )

            if body.apply_instructions and isinstance(metadata.get("instruction_plan"), dict):
                raw_plan = metadata["instruction_plan"]
                raw_opts = metadata.get("migration_options")
                opts = CompetitorMigrationOptions(
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
                    include_episodic=bool(raw_opts.get("include_episodic")) if isinstance(raw_opts, dict) else False,
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
                plan = CompetitorInstructionPlan(
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
            except Exception as exc:
                logger.warning("Post-import diagnostics failed for %s: %s", result.import_batch_id, exc)
                result.diagnostic_status = "failed"
                try:
                    await session_service.save_post_import_diagnostic(
                        import_batch_id=result.import_batch_id,
                        diagnostic_run_id="post-import-diagnostic:failed",
                        diagnostic_status="failed",
                        failed_count=1,
                    )
                except Exception as save_exc:
                    logger.warning("Post-import diagnostic failure state was not persisted: %s", save_exc)
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
        target_agent_id=instruction_result.target_agent_id if instruction_result else None,
        agent_created=instruction_result.agent_created if instruction_result else False,
        global_instructions_updated=(instruction_result.global_instructions_updated if instruction_result else False),
        workspace_rules_written=(instruction_result.workspace_rules_written if instruction_result else 0),
        workspace_rules_skipped=(instruction_result.workspace_rules_skipped if instruction_result else 0),
    )


async def dry_run_rollback_import_memories(
    body: MemoryImportRollbackRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryImportRollbackPreviewResponse:
    """Preview rollback impact for a confirmed memory import batch."""

    async with get_session() as db:
        try:
            result = await MemoryImportSessionService(db).preview_rollback(
                manager=manager,
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryImportRollbackPreviewResponse(
        import_batch_id=result.import_batch_id,
        source=result.source,
        total_items=result.total_items,
        reversible_items=result.reversible_items,
        items_by_type=result.items_by_type,
        profile_keys=result.profile_keys,
        warnings=[
            {
                "code": warning.code,
                "severity": warning.severity,
                "params": warning.params,
            }
            for warning in result.warnings
        ],
        skipped_items=result.skipped_items,
        conflict_items=result.conflict_items,
        missing_items=result.missing_items,
    )


async def rollback_import_memories(
    body: MemoryImportRollbackRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryImportRollbackResponse:
    """Rollback a confirmed memory import batch from its server-bound session."""
    from app.services.memory.import_ledger import MemoryImportLedgerService
    from app.services.migration.instruction_rollback import rollback_instruction_for_batch_metadata

    instructions_rolled_back = False
    imported_agent_deleted = False
    async with get_session() as db:
        try:
            ledger = MemoryImportLedgerService(db)
            batch = await ledger.get_batch(
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
            result = await MemoryImportSessionService(db).rollback_import(
                manager=manager,
                dry_run_id=body.dry_run_id,
                import_batch_id=body.import_batch_id,
            )
            if batch is not None:
                metadata = batch.metadata_json if isinstance(batch.metadata_json, dict) else {}
                instructions_rolled_back = await rollback_instruction_for_batch_metadata(
                    metadata,
                    delete_imported_agent=body.delete_imported_agent,
                )
                if body.delete_imported_agent and instructions_rolled_back:
                    raw = metadata.get("instruction_rollback")
                    if isinstance(raw, dict) and bool(raw.get("agent_created")):
                        imported_agent_deleted = True
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return MemoryImportRollbackResponse(
        import_batch_id=result.import_batch_id,
        rolled_back=result.rolled_back,
        total_rolled_back=result.total_rolled_back,
        source=result.source,
        conflict_items=result.conflict_items,
        missing_items=result.missing_items,
        failed_items=result.failed_items,
        deleted_refs=result.deleted_refs,
        missing_refs=result.missing_refs,
        forbidden_refs=result.forbidden_refs,
        failed_refs=result.failed_refs,
        integrity_status=result.integrity_status,
        instructions_rolled_back=instructions_rolled_back,
        imported_agent_deleted=imported_agent_deleted,
    )
