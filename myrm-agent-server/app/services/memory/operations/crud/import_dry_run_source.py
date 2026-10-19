"""Competitor source normalization for the import dry-run.

[INPUT]
app.services.migration.source.source_payload_loader (POS: 迁移来源载荷加载)
app.services.migration.source.source_payload_split (POS: 迁移来源载荷拆分)
app.services.migration.workspace_bind_candidates (POS: 迁移后工作区绑定候选)

[OUTPUT]
LoadedSource / SideChannels: one competitor payload read once, plus
load_competitor_source / build_side_channels / build_session_metadata.

[POS]
Source half of the dry-run. The handler decides what to preview; this module owns
the reading of a competitor install and the facts the confirm phase replays.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.schemas.memory.archive import MemoryImportMigrationOptions
from app.schemas.memory.import_sources import ImportRequestSource
from app.services.migration.source.source_migration_types import (
    MigrationWizardOptions,
    SourceInstructionPlan,
)
from app.services.migration.workspace_bind_candidates import WorkspaceBindCandidate


@dataclass(frozen=True)
class LoadedSource:
    """One competitor payload normalized into the native import shape."""

    loaded_payload: dict[str, object]
    instruction_plan: SourceInstructionPlan
    migration_opts: MigrationWizardOptions
    import_payload: dict[str, object]
    resolved_source: ImportRequestSource
    competitor: str
    source_has_api_keys: bool
    pending_skills: list[dict[str, object]]
    pending_skills_total: int
    coverage_items: list[dict[str, str]]


@dataclass(frozen=True)
class SideChannels:
    """Non-memory lanes carried through the review session for confirm to replay."""

    mcp_servers_preview: list[dict[str, object]]
    mcp_configs_serialized: list[dict[str, object]]
    model_migration_payload: dict[str, object]
    cron_plan_raw: dict[str, object] | None
    sessions: list[dict[str, object]]
    bind_candidates: list[WorkspaceBindCandidate]


def load_competitor_source(
    payload: dict[str, object],
    migration: MemoryImportMigrationOptions | None,
) -> LoadedSource:
    """Read a competitor install once and normalize it into the native import payload."""

    from app.services.memory.imports.import_adapters import resolve_migration_source
    from app.services.migration.source.source_payload_loader import (
        MAX_PENDING_SKILLS,
        MigrationSourceAccessError,
        build_coverage_items,
        extract_pending_skills,
        load_source_payload,
    )
    from app.services.migration.source.source_payload_split import (
        build_instruction_plan,
        extract_memory_payload,
        has_api_keys,
    )

    try:
        loaded_payload = load_source_payload(payload)
    except MigrationSourceAccessError as exc:
        # A path outside the archive root is a caller error, not a server fault.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pending_skills = extract_pending_skills(loaded_payload)
    pending_skills_total = len(pending_skills)
    if pending_skills_total > MAX_PENDING_SKILLS:
        pending_skills = pending_skills[:MAX_PENDING_SKILLS]

    migration_opts = (
        MigrationWizardOptions(
            target_agent_id=migration.target_agent_id,
            clone_from_agent_id=migration.clone_from_agent_id,
            include_episodic=migration.include_episodic,
            apply_global_instructions=migration.apply_global_instructions,
        )
        if migration is not None
        else MigrationWizardOptions()
    )
    instruction_plan = build_instruction_plan(loaded_payload)
    competitor = str(loaded_payload.get("_source", "")).strip().lower()

    return LoadedSource(
        loaded_payload=loaded_payload,
        instruction_plan=instruction_plan,
        migration_opts=migration_opts,
        import_payload=extract_memory_payload(
            loaded_payload,
            include_episodic=migration_opts.include_episodic,
        ),
        resolved_source=resolve_migration_source(competitor),
        competitor=competitor,
        source_has_api_keys=has_api_keys(loaded_payload),
        pending_skills=pending_skills,
        pending_skills_total=pending_skills_total,
        coverage_items=build_coverage_items(loaded_payload),
    )


def build_side_channels(loaded: LoadedSource) -> SideChannels:
    """Collect the MCP / model / cron / session lanes bound to the review session."""

    from app.services.migration.mcp_config_converter import (
        convert_competitor_mcp_servers,
        mcp_migration_item_to_config_dict,
        mcp_migration_item_to_preview,
    )

    mcp_servers_preview: list[dict[str, object]] = []
    mcp_configs_serialized: list[dict[str, object]] = []
    if isinstance(loaded.instruction_plan.mcp_servers, dict) and loaded.instruction_plan.mcp_servers:
        converted = convert_competitor_mcp_servers(
            loaded.instruction_plan.mcp_servers,
            competitor=loaded.instruction_plan.competitor,
        )
        mcp_servers_preview = [mcp_migration_item_to_preview(item) for item in converted]
        mcp_configs_serialized = [mcp_migration_item_to_config_dict(item) for item in converted]

    model_migration_payload: dict[str, object] = {}
    hermes_cfg = loaded.loaded_payload.get("hermes_config")
    if isinstance(hermes_cfg, dict):
        auxiliary = hermes_cfg.get("auxiliary")
        if isinstance(auxiliary, dict) and auxiliary:
            model_migration_payload["hermes_auxiliary"] = auxiliary
        moa_block = hermes_cfg.get("moa")
        if isinstance(moa_block, dict) and moa_block:
            model_migration_payload["hermes_moa"] = moa_block
    openclaw_cfg = loaded.loaded_payload.get("openclaw_config")
    if isinstance(openclaw_cfg, dict):
        agents_defaults = (openclaw_cfg.get("agents") or {}).get("defaults", {})
        if agents_defaults.get("model") is not None:
            model_migration_payload["openclaw_agents_defaults"] = agents_defaults

    cron_plan_raw = loaded.loaded_payload.get("hermes_cron_plan")
    sessions_raw = loaded.loaded_payload.get("sessions")
    from app.services.migration.workspace_bind_candidates import discover_workspace_bind_candidates

    return SideChannels(
        mcp_servers_preview=mcp_servers_preview,
        mcp_configs_serialized=mcp_configs_serialized,
        model_migration_payload=model_migration_payload,
        cron_plan_raw=cron_plan_raw if isinstance(cron_plan_raw, dict) else None,
        sessions=[item for item in sessions_raw if isinstance(item, dict)] if isinstance(sessions_raw, list) else [],
        bind_candidates=discover_workspace_bind_candidates(loaded.loaded_payload),
    )


def build_session_metadata(
    loaded: LoadedSource,
    channels: SideChannels,
    providers_configured: bool,
) -> dict[str, object]:
    """Freeze everything confirm needs to replay the reviewed lanes."""

    from app.services.migration.workspace_bind_candidates import candidates_to_metadata

    metadata: dict[str, object] = {
        "migration_options": {
            "target_agent_id": loaded.migration_opts.target_agent_id,
            "clone_from_agent_id": loaded.migration_opts.clone_from_agent_id,
            "include_episodic": loaded.migration_opts.include_episodic,
            "apply_global_instructions": loaded.migration_opts.apply_global_instructions,
        },
        "source_has_api_keys": loaded.source_has_api_keys,
        "providers_configured": providers_configured,
        "instruction_plan": {
            "competitor": loaded.instruction_plan.competitor,
            "agent_persona": loaded.instruction_plan.agent_persona,
            "global_supplement": loaded.instruction_plan.global_supplement,
            "workspace_rules": [
                {"filename": rule.filename, "content": rule.content} for rule in loaded.instruction_plan.workspace_rules
            ],
            "mcp_configs": channels.mcp_configs_serialized,
        },
        "migration_competitor": loaded.competitor,
    }
    if channels.model_migration_payload:
        metadata["model_migration"] = channels.model_migration_payload
    if channels.cron_plan_raw is not None:
        metadata["cron_migration"] = channels.cron_plan_raw
    if channels.sessions:
        metadata["session_migration"] = channels.sessions

    metadata["workspace_bind_candidates"] = candidates_to_metadata(channels.bind_candidates)
    return metadata
