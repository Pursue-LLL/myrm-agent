"""Memory import dry-run handler (migration wizard review).

[INPUT]
app.services.memory.operations.crud.import_flows.dry_run_source (POS: 竞品来源归一化)
app.services.memory.operations.crud.import_flows.dry_run_preview (POS: 预览行组装)
app.services.memory.operations.crud.import_flows.paste_lane (POS: 粘贴模型车道)

[OUTPUT]
dry_run_import_memories: review session with mappings, bounded preview samples,
coverage lanes, capped skill bundles and the optional model-assisted paste lane.

[POS]
Preview half of the import lifecycle: decides which lanes a source carries, then
binds the review to a server-side session hash before anything is written.
"""

from __future__ import annotations

from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryImportDryRunRequest,
    MemoryImportDryRunResponse,
    WorkspaceBindCandidate,
)
from app.services.memory.imports.import_sessions import (
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_flows.dry_run_preview import (
    build_instruction_preview,
    build_lane_response_rows,
    build_lane_rows,
    build_session_preview,
    build_token_economics,
    skipped_cron_preview,
)
from app.services.memory.operations.crud.import_flows.dry_run_source import (
    build_session_metadata,
    build_side_channels,
    load_competitor_source,
)
from app.services.memory.operations.crud.import_flows.paste_lane import (
    _is_paste_payload,
    _with_model_extracted_paste_items,
)
from app.services.migration.source.source_migration_types import (
    MigrationLanePreview,
    instruction_char_total,
)
from app.services.migration.source.source_payload_loader import is_source_discovery_payload
from app.services.migration.source.source_secrets_importer import (
    external_source_providers_configured,
)
from app.services.migration.workspace_bind_candidates import to_api_candidates


async def dry_run_import_memories(
    body: MemoryImportDryRunRequest,
) -> MemoryImportDryRunResponse:
    """Preview memory import mapping and bind the review result server-side."""

    is_competitor = is_source_discovery_payload(body.payload)
    providers_configured = await external_source_providers_configured()
    import_payload = body.payload
    resolved_source = body.source
    session_metadata: dict[str, object] = {}
    pending_skills: list[dict[str, object]] = []
    pending_skills_total = 0
    coverage_items: list[dict[str, str]] = []
    workspace_bind_candidates: list[WorkspaceBindCandidate] = []
    lanes: list[MigrationLanePreview] = []
    session_preview: list[dict[str, object]] = []
    instruction_total_chars = 0
    cron_skipped = []
    mcp_servers_preview: list[dict[str, object]] = []

    if body.use_model_extraction and not is_competitor and _is_paste_payload(body.payload, resolved_source):
        import_payload = await _with_model_extracted_paste_items(
            body.payload,
            agent_id=body.migration.target_agent_id if body.migration else None,
        )

    if is_competitor:
        loaded = load_competitor_source(body.payload, body.migration)
        channels = build_side_channels(loaded)
        session_metadata = build_session_metadata(loaded, channels, providers_configured)
        import_payload = loaded.import_payload
        resolved_source = loaded.resolved_source
        pending_skills = loaded.pending_skills
        pending_skills_total = loaded.pending_skills_total
        coverage_items = loaded.coverage_items
        mcp_servers_preview = channels.mcp_servers_preview
        session_preview = build_session_preview(channels.sessions)
        cron_skipped = skipped_cron_preview(channels.cron_plan_raw)
        instruction_total_chars = instruction_char_total(loaded.instruction_plan)
        workspace_bind_candidates = to_api_candidates(channels.bind_candidates)
        lanes = build_lane_rows(
            loaded=loaded,
            channels=channels,
            providers_configured=providers_configured,
        )

    async with get_session() as db:
        dry_run_id, result, payload_hash, expires_at = await MemoryImportSessionService(db).create_dry_run(
            import_payload,
            resolved_source,
            skip_duplicates=body.skip_duplicates,
            session_metadata=session_metadata,
        )

    migration_lanes = (
        build_lane_response_rows(
            lanes,
            memory_status=result.summary.status,
            memory_mapped=result.summary.mapped_items,
            episodic_excluded=body.migration is not None and not body.migration.include_episodic,
        )
        if is_competitor
        else []
    )

    instruction_preview_persona: str | None = None
    instruction_preview_rule_names: list[str] = []
    raw_plan = session_metadata.get("instruction_plan")
    if is_competitor and isinstance(raw_plan, dict):
        instruction_preview_persona, instruction_preview_rule_names = build_instruction_preview(raw_plan)

    return MemoryImportDryRunResponse(
        dry_run_id=dry_run_id,
        payload_hash=payload_hash,
        expires_at=expires_at,
        result=result,
        pending_skills=pending_skills,
        pending_skills_total=pending_skills_total,
        coverage_items=coverage_items,
        migration_lanes=migration_lanes,
        token_economics=build_token_economics(pending_skills_total) if is_competitor else None,
        instruction_preview_persona=instruction_preview_persona,
        instruction_preview_rule_names=instruction_preview_rule_names,
        instruction_total_chars=instruction_total_chars if is_competitor else 0,
        providers_configured=providers_configured,
        mcp_servers_preview=mcp_servers_preview if is_competitor else [],
        workspace_bind_candidates=workspace_bind_candidates,
        cron_skipped=cron_skipped if is_competitor else [],
        session_preview=session_preview,
    )
