"""Memory import readiness recheck and post-import side effects.

[INPUT]
app.services.memory.imports.import_sessions::MemoryImportSessionService (POS: 记忆导入审查会话)

[OUTPUT]
recheck_import_readiness: recompute a batch's readiness from live provider state.
_write_migrated_mcp_configs / _resolve_post_import_moa_overlay_configured /
_apply_model_migration: side effects the confirm flow triggers.

[POS]
Follow-up half of the confirm phase: everything that happens after the reviewed
payload is written, kept separate from the write path itself.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.database.connection import get_session
from app.schemas.memory.archive import (
    MemoryImportReadinessRecheckRequest,
    MemoryImportReadinessRecheckResponse,
)
from app.services.memory.imports.import_sessions import (
    MemoryImportSessionError,
    MemoryImportSessionService,
)

logger = logging.getLogger(__name__)


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
            readiness = await session_service.resolve_live_import_readiness(import_batch_id)
        except MemoryImportSessionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        try:
            await session_service.save_post_import_readiness(
                import_batch_id=import_batch_id,
                readiness_status=readiness.status,
                readiness_issues=[issue.model_dump(mode="json") for issue in readiness.issues],
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


async def _write_migrated_mcp_configs(mcp_configs: list[dict[str, object]]) -> int:
    """Append migrated MCP configs to mcpServers and return newly inserted count."""

    from app.services.config.service import config_service

    record = await config_service.get("mcpServers")
    existing: list[dict[str, object]] = []
    if record is not None and isinstance(record.value, list):
        existing = list(record.value)

    existing_names = {str(cfg.get("name", "")) for cfg in existing if isinstance(cfg, dict)}

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
            result = await migrate_hermes_auxiliary_models({"auxiliary": hermes_auxiliary})
            if result.migrated_slots:
                logger.info(
                    "Model migration: %d Hermes auxiliary slots applied",
                    len(result.migrated_slots),
                )
        except Exception as exc:
            logger.warning("Hermes auxiliary model migration failed (non-fatal): %s", exc)

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
                logger.info("Model migration: OpenClaw default model → %s", migrated_model)
        except Exception as exc:
            logger.warning("OpenClaw default model migration failed (non-fatal): %s", exc)


# Model extraction is a single LLM call, so the pasted text is only sent when it
# fits a bounded budget; longer pastes keep the deterministic parser instead of
# risking a failed or oversized call.
_MODEL_EXTRACTION_MAX_CHARS = 40_000
