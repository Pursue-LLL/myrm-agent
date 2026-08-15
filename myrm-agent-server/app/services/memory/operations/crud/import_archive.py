"""Memory CRUD — import archive.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::UpdateMemoryStatusRequest (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::TasteSummaryResponse (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.archive::*Import* / *Archive* (POS: 记忆归档与导入 API Schema 层)
app.services.migration.source.source_payload_split (POS: 竞品 payload 指令/记忆车道拆分)
app.services.migration.instruction_writer (POS: 竞品指令车道写入 Agent 与全局设置)
app.services.migration.memory_import_binding (POS: 迁移事实记忆的全局 namespace 绑定)
app.services.memory.operations.crud.import_readiness (POS: 记忆导入就绪合同构建层。负责把 provider、diagnostic、MCP 与规则跳过事实归并为可执行门禁状态。)

[OUTPUT]
memory CRUD handler functions、状态变更、偏好摘要、偏好管理、服务端绑定导入、Memory Archive、导入后诊断与运行就绪合同、readiness-recheck、回滚预演端点

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
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
)

from app.database.connection import get_session
from app.schemas.memory.archive import (
    CronImportSummary,
    CronMigrationSkippedPreviewItem,
    MemoryArchiveDryRunRequest,
    MemoryArchiveDryRunResponse,
    MemoryArchiveExportResponse,
    MemoryImportConfirmRequest,
    MemoryImportConfirmResponse,
    MemoryImportDryRunRequest,
    MemoryImportDryRunResponse,
    MemoryImportReadiness,
    MemoryImportReadinessRecheckRequest,
    MemoryImportReadinessRecheckResponse,
    MemoryImportRequest,
    MemoryImportResponse,
    MemoryImportRollbackPreviewResponse,
    MemoryImportRollbackRequest,
    MemoryImportRollbackResponse,
    MigrationLanePreviewItem,
    TokenEconomicsComparison,
    WorkspaceBindCandidate,
)
from app.schemas.memory.crud import (
    MEMORY_EXPORT_VERSION,
    MemoryExportResponse,
)
from app.services.memory.archive.archive import MemoryArchiveService
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
from app.services.memory.imports.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionError,
    MemoryImportSessionService,
)
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _record_memory_event
from app.services.memory.operations.crud.import_readiness import build_import_readiness
from app.services.migration.source.source_secrets_importer import (
    external_source_providers_configured,
)

logger = logging.getLogger(__name__)

_COMPETITOR_AVG_SKILL_TOKENS = 500
_MYRM_AVG_INDEX_TOKENS = 30


def _cron_skipped_preview_from_plan(
    raw: dict[str, object] | None,
) -> list[CronMigrationSkippedPreviewItem]:
    if not isinstance(raw, dict):
        return []
    from app.services.migration.hermes.hermes_cron_converter import (
        HermesCronMigrationPlan,
        cron_skipped_preview_rows,
    )

    plan = HermesCronMigrationPlan.from_metadata_dict(raw)
    return [
        CronMigrationSkippedPreviewItem(
            name=str(row["name"]), reason=str(row["reason"])
        )
        for row in cron_skipped_preview_rows(plan)
        if row.get("name") and row.get("reason")
    ]


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
    return MemoryExportResponse(
        version=MEMORY_EXPORT_VERSION, data=data, total_count=total
    )


async def export_rules_safe(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
    rule_ids: str | None = Query(
        default=None, description="Comma-separated rule IDs to export"
    ),
    output_format: str = Query(
        default="markdown", description="Output format: markdown or json"
    ),
) -> StreamingResponse:
    """Export procedural rules with privacy sanitization for safe sharing."""
    ids_list = (
        [r.strip() for r in rule_ids.split(",") if r.strip()] if rule_ids else None
    )
    results = await manager.export_rules_safe(
        agent_id=agent_id,
        rule_ids=ids_list,
        output_format=output_format,
    )
    if not results:
        raise HTTPException(status_code=404, detail="No rules found matching criteria")

    ext = "json" if output_format == "json" else "md"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            filename = f"rule_{str(item['id'])[:8]}.{ext}"
            zf.writestr(filename, str(item["rendered"]))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="rules_safe_{len(results)}.zip"',
            "X-Export-Count": str(len(results)),
        },
    )


async def preview_rules_safe(
    manager: MemoryManager = Depends(get_crud_memory_manager),
    agent_id: str | None = Query(default=None, description="Filter by agent scope"),
    rule_ids: str | None = Query(
        default=None, description="Comma-separated rule IDs to preview"
    ),
    output_format: str = Query(
        default="markdown", description="Output format: markdown or json"
    ),
) -> list[dict[str, object]]:
    """Preview sanitized rules without downloading (for frontend diff display)."""
    ids_list = (
        [r.strip() for r in rule_ids.split(",") if r.strip()] if rule_ids else None
    )
    return await manager.export_rules_safe(
        agent_id=agent_id,
        rule_ids=ids_list,
        output_format=output_format,
    )


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


async def dry_run_import_memories(
    body: MemoryImportDryRunRequest,
) -> MemoryImportDryRunResponse:
    """Preview memory import mapping and bind the review result server-side."""

    from app.services.memory.imports.import_adapters import resolve_migration_source
    from app.services.migration.source.source_migration_types import (
        MigrationLanePreview,
        MigrationWizardOptions,
        build_lane_previews,
        instruction_char_total,
    )
    from app.services.migration.source.source_payload_loader import (
        build_coverage_items,
        extract_pending_skills,
        is_source_discovery_payload,
        load_source_payload,
    )
    from app.services.migration.source.source_payload_split import (
        build_instruction_plan,
        extract_memory_payload,
        has_api_keys,
    )
    from app.services.migration.source.source_secrets_importer import (
        external_source_providers_configured,
    )

    pending_skills: list[dict[str, object]] = []
    coverage_items: list[dict[str, str]] = []
    migration_lanes: list[MigrationLanePreviewItem] = []
    import_payload = body.payload
    session_metadata: dict[str, object] = {}
    resolved_source = body.source
    lane_previews = []
    is_competitor = is_source_discovery_payload(body.payload)
    instruction_total_chars = 0
    providers_configured = await external_source_providers_configured()
    workspace_bind_candidates: list[WorkspaceBindCandidate] = []
    cron_skipped_preview: list[CronMigrationSkippedPreviewItem] = []

    if is_competitor:
        loaded_payload = load_source_payload(body.payload)
        pending_skills = extract_pending_skills(loaded_payload)
        coverage_items = build_coverage_items(loaded_payload)

        migration_opts = (
            MigrationWizardOptions(
                target_agent_id=body.migration.target_agent_id,
                clone_from_agent_id=body.migration.clone_from_agent_id,
                include_episodic=body.migration.include_episodic,
                apply_global_instructions=body.migration.apply_global_instructions,
            )
            if body.migration is not None
            else MigrationWizardOptions()
        )
        instruction_plan = build_instruction_plan(loaded_payload)
        import_payload = extract_memory_payload(
            loaded_payload,
            include_episodic=migration_opts.include_episodic,
        )
        competitor = str(loaded_payload.get("_source", "")).strip().lower()
        resolved_source = resolve_migration_source(competitor)
        from app.services.migration.mcp_config_converter import (
            convert_competitor_mcp_servers,
            mcp_migration_item_to_config_dict,
            mcp_migration_item_to_preview,
        )

        mcp_servers_preview: list[dict[str, object]] = []
        mcp_configs_serialized: list[dict[str, object]] = []
        if (
            isinstance(instruction_plan.mcp_servers, dict)
            and instruction_plan.mcp_servers
        ):
            converted = convert_competitor_mcp_servers(
                instruction_plan.mcp_servers,
                competitor=instruction_plan.competitor,
            )
            mcp_servers_preview = [
                mcp_migration_item_to_preview(item) for item in converted
            ]
            mcp_configs_serialized = [
                mcp_migration_item_to_config_dict(item) for item in converted
            ]

        model_migration_payload: dict[str, object] = {}
        hermes_cfg = loaded_payload.get("hermes_config")
        if isinstance(hermes_cfg, dict):
            auxiliary = hermes_cfg.get("auxiliary")
            if isinstance(auxiliary, dict) and auxiliary:
                model_migration_payload["hermes_auxiliary"] = auxiliary
            moa_block = hermes_cfg.get("moa")
            if isinstance(moa_block, dict) and moa_block:
                model_migration_payload["hermes_moa"] = moa_block
        openclaw_cfg = loaded_payload.get("openclaw_config")
        if isinstance(openclaw_cfg, dict):
            agents_defaults = (openclaw_cfg.get("agents") or {}).get("defaults", {})
            if agents_defaults.get("model") is not None:
                model_migration_payload["openclaw_agents_defaults"] = agents_defaults

        source_has_api_keys = has_api_keys(loaded_payload)
        providers_configured = await external_source_providers_configured()
        session_metadata = {
            "migration_options": {
                "target_agent_id": migration_opts.target_agent_id,
                "clone_from_agent_id": migration_opts.clone_from_agent_id,
                "include_episodic": migration_opts.include_episodic,
                "apply_global_instructions": migration_opts.apply_global_instructions,
            },
            "source_has_api_keys": source_has_api_keys,
            "providers_configured": providers_configured,
            "instruction_plan": {
                "competitor": instruction_plan.competitor,
                "agent_persona": instruction_plan.agent_persona,
                "global_supplement": instruction_plan.global_supplement,
                "workspace_rules": [
                    {"filename": rule.filename, "content": rule.content}
                    for rule in instruction_plan.workspace_rules
                ],
                "mcp_configs": mcp_configs_serialized,
            },
        }
        if model_migration_payload:
            session_metadata["model_migration"] = model_migration_payload
        session_metadata["migration_competitor"] = competitor
        cron_plan_raw = loaded_payload.get("hermes_cron_plan")
        if isinstance(cron_plan_raw, dict):
            session_metadata["cron_migration"] = cron_plan_raw
            cron_skipped_preview = _cron_skipped_preview_from_plan(cron_plan_raw)
        from app.services.migration.workspace_bind_candidates import (
            candidates_to_metadata,
            discover_workspace_bind_candidates,
        )

        bind_candidates = discover_workspace_bind_candidates(loaded_payload)
        workspace_bind_candidates = [
            WorkspaceBindCandidate(
                path=item.path,
                label=item.label,
                has_obsidian_config=item.has_obsidian_config,
                markdown_file_count=item.markdown_file_count,
            )
            for item in bind_candidates
        ]
        session_metadata["workspace_bind_candidates"] = candidates_to_metadata(
            bind_candidates
        )
        instruction_total_chars = instruction_char_total(instruction_plan)
        lane_previews = build_lane_previews(
            instruction=instruction_plan,
            memory_mapped=0,
            memory_status="pending",
            skill_count=len(pending_skills),
            has_api_keys=source_has_api_keys,
            providers_ready=providers_configured,
            include_episodic=migration_opts.include_episodic,
        )
        if competitor == "hermes":
            importable_count = 0
            skipped_count = 0
            if isinstance(cron_plan_raw, dict):
                importable_raw = cron_plan_raw.get("importable")
                skipped_raw = cron_plan_raw.get("skipped")
                if isinstance(importable_raw, list):
                    importable_count = len(importable_raw)
                if isinstance(skipped_raw, list):
                    skipped_count = len(skipped_raw)
            if importable_count > 0:
                cron_detail = (
                    f"{importable_count} scheduled task(s) will import paused"
                    + (f"; {skipped_count} skipped" if skipped_count else "")
                )
                cron_status = "ready"
            elif skipped_count > 0:
                cron_detail = f"{skipped_count} cron job(s) detected but not importable"
                cron_status = "warning"
            else:
                cron_detail = "no cron jobs detected"
                cron_status = "missing"
            lane_previews = [
                *lane_previews,
                MigrationLanePreview(
                    lane="cron",
                    status=cron_status,
                    label="cron_lane",
                    detail=cron_detail,
                ),
            ]

    async with get_session() as db:
        dry_run_id, result, payload_hash, expires_at = await MemoryImportSessionService(
            db
        ).create_dry_run(
            import_payload,
            resolved_source,
            skip_duplicates=body.skip_duplicates,
            session_metadata=session_metadata,
        )

    if is_competitor:
        migration_lanes = [
            MigrationLanePreviewItem(
                lane=lane.lane,
                status=(
                    result.summary.status if lane.lane == "memory" else lane.status
                ),
                label=lane.label,
                detail=(
                    f"{result.summary.mapped_items} mapped item(s)"
                    + (
                        ", episodic excluded"
                        if body.migration is not None
                        and not body.migration.include_episodic
                        else ""
                    )
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

    token_economics: TokenEconomicsComparison | None = None
    if is_competitor and pending_skills:
        skill_count = len(pending_skills)
        source_tokens = skill_count * _COMPETITOR_AVG_SKILL_TOKENS
        myrm_tokens = skill_count * _MYRM_AVG_INDEX_TOKENS
        savings = (
            round((1 - myrm_tokens / source_tokens) * 100, 1)
            if source_tokens > 0
            else 0.0
        )
        token_economics = TokenEconomicsComparison(
            skill_count=skill_count,
            source_tokens_per_turn=source_tokens,
            myrm_tokens_per_turn=myrm_tokens,
            savings_percent=savings,
        )

    return MemoryImportDryRunResponse(
        dry_run_id=dry_run_id,
        payload_hash=payload_hash,
        expires_at=expires_at,
        result=result,
        pending_skills=pending_skills,
        coverage_items=coverage_items,
        migration_lanes=migration_lanes,
        token_economics=token_economics,
        instruction_preview_persona=instruction_preview_persona,
        instruction_preview_rule_names=instruction_preview_rule_names,
        instruction_total_chars=instruction_total_chars if is_competitor else 0,
        providers_configured=providers_configured,
        mcp_servers_preview=mcp_servers_preview if is_competitor else [],
        workspace_bind_candidates=workspace_bind_candidates,
        cron_skipped=cron_skipped_preview if is_competitor else [],
    )


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
            metadata = await session_service.get_pending_session_metadata(
                body.dry_run_id
            )
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
                for item in candidates_from_metadata(
                    metadata.get("workspace_bind_candidates")
                )
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
                        if isinstance(raw_opts, dict)
                        and raw_opts.get("target_agent_id")
                        else None
                    ),
                    clone_from_agent_id=(
                        str(raw_opts.get("clone_from_agent_id", "builtin-general"))
                        if isinstance(raw_opts, dict)
                        else "builtin-general"
                    ),
                    include_episodic=(
                        bool(raw_opts.get("include_episodic"))
                        if isinstance(raw_opts, dict)
                        else False
                    ),
                    apply_global_instructions=(
                        bool(raw_opts.get("apply_global_instructions", True))
                        if isinstance(raw_opts, dict)
                        else True
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
                                    WorkspaceRuleWrite(
                                        filename=filename, content=content
                                    ),
                                )
                mcp_configs_raw = raw_plan.get("mcp_configs")
                mcp_configs_to_write: list[dict[str, object]] = []
                if isinstance(mcp_configs_raw, list):
                    mcp_configs_to_write = [
                        item
                        for item in mcp_configs_raw
                        if isinstance(item, dict) and item.get("name")
                    ]

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
                        mcp_imported_disabled_count = await _write_migrated_mcp_configs(
                            mcp_configs_to_write
                        )
                    except Exception as mcp_exc:
                        logger.warning(
                            "MCP config migration write failed (non-fatal): %s", mcp_exc
                        )

                model_migration_data = metadata.get("model_migration")
                if isinstance(model_migration_data, dict):
                    moa_target_agent_id = (
                        instruction_result.target_agent_id
                        if instruction_result
                        else None
                    )
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

                cron_plan = HermesCronMigrationPlan.from_metadata_dict(
                    cron_migration_raw
                )
                migration_opts_raw = metadata.get("migration_options")
                cron_agent_id: str | None = None
                if instruction_result and instruction_result.target_agent_id:
                    cron_agent_id = instruction_result.target_agent_id
                elif isinstance(migration_opts_raw, dict) and migration_opts_raw.get(
                    "target_agent_id"
                ):
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

            try:
                snapshot = await MemoryCommandCenterService(
                    db, manager
                ).build_snapshot()
                diagnostic_run = await MemoryDiagnosticsService(
                    db, manager
                ).run_diagnostics(
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
            workspace_rules_skipped_count = (
                instruction_result.workspace_rules_skipped if instruction_result else 0
            )
            providers_configured = await external_source_providers_configured()
            migration_competitor_raw = metadata.get("migration_competitor")
            migration_competitor = (
                migration_competitor_raw.strip()
                if isinstance(migration_competitor_raw, str)
                and migration_competitor_raw.strip()
                else None
            )
            if migration_competitor is None and isinstance(raw_instruction_plan, dict):
                migration_competitor = (
                    str(raw_instruction_plan.get("competitor", "")).strip().lower()
                    or None
                )
            moa_overlay_configured: bool | None = None
            if migration_competitor == "hermes":
                moa_overlay_configured = (
                    await _resolve_post_import_moa_overlay_configured(
                        (
                            instruction_result.target_agent_id
                            if instruction_result
                            else None
                        ),
                        metadata.get("model_migration"),
                    )
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
                    readiness_issues=[
                        issue.model_dump(mode="json") for issue in readiness.issues
                    ],
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
        target_agent_id=(
            instruction_result.target_agent_id if instruction_result else None
        ),
        agent_created=instruction_result.agent_created if instruction_result else False,
        global_instructions_updated=(
            instruction_result.global_instructions_updated
            if instruction_result
            else False
        ),
        workspace_rules_written=(
            instruction_result.workspace_rules_written if instruction_result else 0
        ),
        workspace_rules_skipped=(
            instruction_result.workspace_rules_skipped if instruction_result else 0
        ),
        readiness=readiness,
        workspace_bind_candidates=workspace_bind_candidates,
        cron_import_summary=cron_import_summary,
    )


async def recheck_import_readiness(
    body: MemoryImportReadinessRecheckRequest,
) -> MemoryImportReadinessRecheckResponse:
    """Re-evaluate post-import execution readiness using current runtime facts."""

    import_batch_id = body.import_batch_id.strip()
    if not import_batch_id:
        raise HTTPException(status_code=400, detail="Import batch id is required.")

    async with get_session() as db:
        session_service = MemoryImportSessionService(db)
        try:
            readiness = await session_service.resolve_live_import_readiness(
                import_batch_id
            )
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        try:
            await session_service.save_post_import_readiness(
                import_batch_id=import_batch_id,
                readiness_status=readiness.status,
                readiness_issues=[
                    issue.model_dump(mode="json") for issue in readiness.issues
                ],
            )
        except Exception as readiness_exc:
            logger.warning(
                "Post-import readiness recheck was not persisted for %s: %s",
                import_batch_id,
                readiness_exc,
            )

    return MemoryImportReadinessRecheckResponse(
        import_batch_id=import_batch_id,
        readiness=readiness,
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
    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.migration.instruction_rollback import (
        rollback_instruction_for_batch_metadata,
    )

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
                metadata = (
                    batch.metadata_json if isinstance(batch.metadata_json, dict) else {}
                )
                instructions_rolled_back = (
                    await rollback_instruction_for_batch_metadata(
                        metadata,
                        delete_imported_agent=body.delete_imported_agent,
                    )
                )
                cron_raw = metadata.get("cron_rollback")
                if isinstance(cron_raw, dict):
                    from app.services.migration.hermes.hermes_cron_migration import (
                        rollback_hermes_cron_migration,
                    )

                    await rollback_hermes_cron_migration(cron_raw)
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


async def _write_migrated_mcp_configs(mcp_configs: list[dict[str, object]]) -> int:
    """Append migrated MCP configs to mcpServers and return newly inserted count."""

    from app.services.config.service import config_service

    record = await config_service.get("mcpServers")
    existing: list[dict[str, object]] = []
    if record is not None and isinstance(record.value, list):
        existing = list(record.value)

    existing_names = {
        str(cfg.get("name", "")) for cfg in existing if isinstance(cfg, dict)
    }

    inserted_count = 0
    for cfg in mcp_configs:
        name = str(cfg.get("name", "")).strip()
        if not name or name in existing_names:
            continue
        entry = {**cfg, "enabled": False}
        existing.append(entry)
        existing_names.add(name)
        inserted_count += 1

    await config_service.set("mcpServers", existing)
    return inserted_count


async def _resolve_post_import_moa_overlay_configured(
    target_agent_id: str | None,
    model_migration_data: object,
) -> bool:
    """Return whether the migrated agent has MoA overlay refs after import."""
    if target_agent_id:
        from app.services.agent.agent_service import AgentService
        from app.services.migration.hermes.hermes_moa_migrator import (
            agent_has_moa_overlay_refs,
        )

        agent = await AgentService.get_agent_by_id(target_agent_id)
        if agent is not None and agent_has_moa_overlay_refs(
            agent.engine_params if isinstance(agent.engine_params, dict) else None
        ):
            return True

    if isinstance(model_migration_data, dict):
        hermes_moa = model_migration_data.get("hermes_moa")
        if isinstance(hermes_moa, dict):
            from app.services.migration.hermes.hermes_moa_migrator import (
                build_moa_overlay_from_hermes_config,
            )

            if build_moa_overlay_from_hermes_config(hermes_moa) is not None:
                return False

    return True


async def _apply_model_migration(
    model_data: dict[str, object],
    *,
    target_agent_id: str | None = None,
) -> None:
    """Apply model configuration migration from competitor payload (non-fatal)."""
    from app.services.migration.source.source_model_migrator import (
        migrate_hermes_auxiliary_models,
        migrate_openclaw_default_model,
    )

    hermes_auxiliary = model_data.get("hermes_auxiliary")
    if isinstance(hermes_auxiliary, dict) and hermes_auxiliary:
        try:
            result = await migrate_hermes_auxiliary_models(
                {"auxiliary": hermes_auxiliary}
            )
            if result.migrated_slots:
                logger.info(
                    "Model migration: %d Hermes auxiliary slots applied",
                    len(result.migrated_slots),
                )
        except Exception as exc:
            logger.warning(
                "Hermes auxiliary model migration failed (non-fatal): %s", exc
            )

    hermes_moa = model_data.get("hermes_moa")
    if isinstance(hermes_moa, dict) and target_agent_id:
        try:
            from app.services.migration.hermes.hermes_moa_migrator import (
                migrate_hermes_moa_overlay,
            )

            moa_result = await migrate_hermes_moa_overlay(
                {"moa": hermes_moa},
                target_agent_id,
            )
            if moa_result.configured and moa_result.reference_count:
                logger.info(
                    "Model migration: Hermes MoA preset=%s refs=%d → agent %s",
                    moa_result.preset_name,
                    moa_result.reference_count,
                    target_agent_id,
                )
        except Exception as exc:
            logger.warning("Hermes MoA overlay migration failed (non-fatal): %s", exc)

    openclaw_defaults = model_data.get("openclaw_agents_defaults")
    if isinstance(openclaw_defaults, dict):
        try:
            migrated_model = await migrate_openclaw_default_model(
                {"agents": {"defaults": openclaw_defaults}},
            )
            if migrated_model:
                logger.info(
                    "Model migration: OpenClaw default model → %s", migrated_model
                )
        except Exception as exc:
            logger.warning(
                "OpenClaw default model migration failed (non-fatal): %s", exc
            )
