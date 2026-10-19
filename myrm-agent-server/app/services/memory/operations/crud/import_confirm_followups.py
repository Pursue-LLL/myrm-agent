"""Cron, session and post-import readiness lanes of the confirm handler.

[INPUT]
app.services.migration.hermes.hermes_cron_migration (POS: Hermes cron 迁移)
app.services.migration.session_lane (POS: 会话迁移)
app.services.memory.command_center.command_center (POS: 记忆指挥中心快照)
app.services.memory.diagnostics.diagnostics (POS: 记忆诊断)

[OUTPUT]
apply_cron_lane / apply_session_lane / run_post_import_diagnostic / build_readiness /
persist_readiness: the follow-up writes and the readiness contract they feed.

[POS]
Follow-up lanes of the confirm phase. Each one is independently failable and
reports its own outcome, so a partial import still ends in an honest readiness
verdict instead of a blanket failure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.memory import MemoryManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.archive import CronImportSummary, MemoryImportReadiness
from app.services.memory.imports.import_sessions import (
    ImportReadinessRecheckFacts,
    MemoryImportSessionService,
)
from app.services.memory.operations.crud.import_readiness import build_import_readiness
from app.services.memory.operations.crud.import_side_effects import (
    _resolve_post_import_moa_overlay_configured,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SessionLaneOutcome:
    """Chats created by the session lane, ready for the response and the ledger."""

    imported_count: int
    chat_ids: list[str]


@dataclass(frozen=True)
class DiagnosticOutcome:
    """Post-import diagnostic state; `failed` is recorded, never raised."""

    status: str | None
    run_id: str | None
    failed_count: int


async def apply_cron_lane(
    db: AsyncSession,
    *,
    import_batch_id: str,
    cron_plan: dict[str, object],
    target_agent_id: str | None,
    fallback_agent_id: str | None,
) -> CronImportSummary:
    """Import Hermes cron jobs paused, and record what can be rolled back."""

    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.migration.hermes.hermes_cron_converter import HermesCronMigrationPlan
    from app.services.migration.hermes.hermes_cron_migration import apply_hermes_cron_migration_plan

    plan = HermesCronMigrationPlan.from_metadata_dict(cron_plan)
    apply_result = await apply_hermes_cron_migration_plan(
        plan,
        agent_id=target_agent_id or fallback_agent_id,
    )
    if apply_result.created_job_ids or apply_result.failed_count:
        await MemoryImportLedgerService(db).merge_batch_metadata(
            import_batch_id,
            {"cron_rollback": apply_result.to_metadata_dict()},
        )
    return CronImportSummary(
        imported_count=len(apply_result.created_job_ids),
        failed_count=apply_result.failed_count,
        skipped_count=len(plan.skipped),
    )


async def apply_session_lane(
    db: AsyncSession,
    *,
    import_batch_id: str,
    sessions: list[dict[str, object]],
    target_workspace_override: str | None,
    target_agent_id: str | None,
) -> SessionLaneOutcome:
    """Persist reviewed transcripts as native chats and record their ids for rollback."""

    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.migration.session_lane import SessionMigrationService

    result = await SessionMigrationService(db).confirm_sessions(
        sessions=sessions,
        target_workspace_override=target_workspace_override,
        target_agent_id=target_agent_id,
    )
    if result.created_chat_ids:
        await MemoryImportLedgerService(db).merge_batch_metadata(
            import_batch_id,
            {"session_rollback": {"created_chat_ids": result.created_chat_ids}},
        )
    return SessionLaneOutcome(imported_count=result.imported_count, chat_ids=result.created_chat_ids)


async def run_post_import_diagnostic(
    db: AsyncSession,
    *,
    manager: MemoryManager,
    session_service: MemoryImportSessionService,
    import_batch_id: str,
) -> DiagnosticOutcome:
    """Run diagnostics on the imported store; a failure is recorded, never raised."""

    from app.services.memory.command_center.command_center import MemoryCommandCenterService
    from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService

    try:
        snapshot = await MemoryCommandCenterService(db, manager).build_snapshot()
        diagnostic = await MemoryDiagnosticsService(db, manager).run_diagnostics(
            health_cache_status=snapshot.health.cache_status,
            runtime=snapshot.runtime,
        )
        await session_service.save_post_import_diagnostic(
            import_batch_id=import_batch_id,
            diagnostic_run_id=diagnostic.id,
            diagnostic_status=diagnostic.status,
            failed_count=diagnostic.failed_count,
        )
        return DiagnosticOutcome(
            status=diagnostic.status,
            run_id=diagnostic.id,
            failed_count=diagnostic.failed_count,
        )
    except Exception as exc:
        logger.warning("Post-import diagnostics failed for %s: %s", import_batch_id, exc)
        await _record_diagnostic_failure(session_service, import_batch_id)
        return DiagnosticOutcome(status="failed", run_id=None, failed_count=1)


async def _record_diagnostic_failure(
    session_service: MemoryImportSessionService,
    import_batch_id: str,
) -> None:
    try:
        await session_service.save_post_import_diagnostic(
            import_batch_id=import_batch_id,
            diagnostic_run_id="post-import-diagnostic:failed",
            diagnostic_status="failed",
            failed_count=1,
        )
    except Exception as save_exc:
        logger.warning("Post-import diagnostic failure state was not persisted: %s", save_exc)


def resolve_migration_competitor(metadata: dict[str, object]) -> str | None:
    """Stored competitor id, falling back to the reviewed instruction plan."""

    raw = metadata.get("migration_competitor")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raw_plan = metadata.get("instruction_plan")
    if isinstance(raw_plan, dict):
        return str(raw_plan.get("competitor", "")).strip().lower() or None
    return None


async def build_readiness(
    *,
    providers_configured: bool,
    source_has_api_keys: bool,
    diagnostic_status: str | None,
    diagnostic_failed_count: int,
    mcp_config_count: int,
    workspace_rules_skipped: int,
    migration_competitor: str | None,
    target_agent_id: str | None,
    model_migration: object,
) -> MemoryImportReadiness:
    """Aggregate provider/diagnostic/MCP/rules facts into the post-import verdict."""

    moa_overlay_configured: bool | None = None
    if migration_competitor == "hermes":
        moa_overlay_configured = await _resolve_post_import_moa_overlay_configured(
            target_agent_id,
            model_migration,
        )
    return build_import_readiness(
        providers_configured=providers_configured,
        source_has_api_keys=source_has_api_keys,
        diagnostic_status=diagnostic_status,
        diagnostic_failed_count=diagnostic_failed_count,
        mcp_config_count=mcp_config_count,
        workspace_rules_skipped=workspace_rules_skipped,
        migration_competitor=migration_competitor,
        moa_overlay_configured=moa_overlay_configured,
    )


async def persist_readiness(
    session_service: MemoryImportSessionService,
    *,
    import_batch_id: str,
    readiness: MemoryImportReadiness,
    recheck_facts: ImportReadinessRecheckFacts,
) -> None:
    """Store the verdict and the facts a later recheck needs; failure is non-fatal."""

    try:
        await session_service.save_post_import_readiness(
            import_batch_id=import_batch_id,
            readiness_status=readiness.status,
            readiness_issues=[issue.model_dump(mode="json") for issue in readiness.issues],
            recheck_facts=recheck_facts,
        )
    except Exception as exc:
        logger.warning("Post-import readiness state was not persisted for %s: %s", import_batch_id, exc)
