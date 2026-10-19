"""Memory import dry-run handler (migration wizard review).

[INPUT]
app.services.memory.operations.crud.import_session_data (POS: 记忆导入会话数据)
app.services.migration.source.source_payload_loader (POS: 迁移来源载荷加载)

[OUTPUT]
dry_run_import_memories: review session with mappings, bounded preview samples,
coverage lanes, capped skill bundles and the optional model-assisted paste lane.

[POS]
Preview half of the import lifecycle: normalizes any source into native buckets
and binds the review to a server-side session hash before anything is written.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.database.connection import get_session
from app.schemas.memory.archive import (
    CronMigrationSkippedPreviewItem,
    MemoryImportDryRunRequest,
    MemoryImportDryRunResponse,
    MigrationLanePreviewItem,
    TokenEconomicsComparison,
    WorkspaceBindCandidate,
)
from app.services.memory.imports.import_sessions import (
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_paste_lane import (
    _is_paste_payload,
    _with_model_extracted_paste_items,
)
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
        CronMigrationSkippedPreviewItem(name=str(row["name"]), reason=str(row["reason"]))
        for row in cron_skipped_preview_rows(plan)
        if row.get("name") and row.get("reason")
    ]


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
        MAX_PENDING_SKILLS,
        MigrationSourceAccessError,
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

    pending_skills: list[dict[str, object]] = []
    pending_skills_total = 0
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
    session_preview: list[dict[str, object]] = []

    if body.use_model_extraction and not is_competitor and _is_paste_payload(body.payload, resolved_source):
        import_payload = await _with_model_extracted_paste_items(
            body.payload,
            agent_id=body.migration.target_agent_id if body.migration else None,
        )

    if is_competitor:
        try:
            loaded_payload = load_source_payload(body.payload)
        except MigrationSourceAccessError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        pending_skills = extract_pending_skills(loaded_payload)
        pending_skills_total = len(pending_skills)
        if pending_skills_total > MAX_PENDING_SKILLS:
            pending_skills = pending_skills[:MAX_PENDING_SKILLS]
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
        if isinstance(instruction_plan.mcp_servers, dict) and instruction_plan.mcp_servers:
            converted = convert_competitor_mcp_servers(
                instruction_plan.mcp_servers,
                competitor=instruction_plan.competitor,
            )
            mcp_servers_preview = [mcp_migration_item_to_preview(item) for item in converted]
            mcp_configs_serialized = [mcp_migration_item_to_config_dict(item) for item in converted]

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
                    {"filename": rule.filename, "content": rule.content} for rule in instruction_plan.workspace_rules
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
        session_metadata["workspace_bind_candidates"] = candidates_to_metadata(bind_candidates)
        instruction_total_chars = instruction_char_total(instruction_plan)
        lane_previews = build_lane_previews(
            instruction=instruction_plan,
            memory_mapped=0,
            memory_status="pending",
            skill_count=pending_skills_total or len(pending_skills),
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
                cron_detail = f"{importable_count} scheduled task(s) will import paused" + (
                    f"; {skipped_count} skipped" if skipped_count else ""
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

        sessions_data = loaded_payload.get("sessions")
        if isinstance(sessions_data, list) and sessions_data:
            session_preview = [
                {
                    "session_id": str(s.get("session_id", "")),
                    "title": str(s.get("title", "")),
                    "turn_count": len(s.get("turns") or []),
                    "tool_call_count": int(s.get("total_tool_calls") or 0),
                    "source_platform": str(s.get("source_platform", "")),
                    "workspace_hint": s.get("detected_workspace_hint"),
                }
                for s in sessions_data
                if isinstance(s, dict)
            ]
            session_metadata["session_migration"] = sessions_data
            lane_previews.append(
                MigrationLanePreview(
                    lane="session",
                    status="ready",
                    label="session_lane",
                    detail=f"{len(session_preview)} session(s) ready for resumption",
                ),
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

    token_economics: TokenEconomicsComparison | None = None
    if is_competitor and pending_skills_total:
        skill_count = pending_skills_total
        source_tokens = skill_count * _COMPETITOR_AVG_SKILL_TOKENS
        myrm_tokens = skill_count * _MYRM_AVG_INDEX_TOKENS
        savings = round((1 - myrm_tokens / source_tokens) * 100, 1) if source_tokens > 0 else 0.0
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
        pending_skills_total=pending_skills_total,
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
        session_preview=session_preview,
    )
