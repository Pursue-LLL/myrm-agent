"""Migration readiness preflight — emit capability_gap SSE before Agent execution.

[INPUT]
- app.services.agent.params.models::MigrationReadinessAnchorRequest (POS: one-shot migration readiness anchor on AgentRequest)
- app.services.agent.stream_session.entitlement_gap_preflight::get_capability_gap_emission_tracker (POS: entitlement gap 预检与 capability_gap SSE 发射)
- app.services.memory.imports.import_sessions::MemoryImportSessionService (POS: resolve live post-import readiness)

[OUTPUT]
- build_migration_readiness_gap_sse_event_from_readiness: build SSE from live readiness contract
- resolve_and_build_migration_readiness_gap_sse_event: async live resolve + SSE for first-turn migration chat

[POS]
Soft gate for post-migration first chat: when the client sends migration_readiness_anchor with
import_batch_id, live-resolve readiness and emit capability_gap with issue-aware settings CTA.
Does not block stream execution or modify Turn1 tool bindings.
"""

from __future__ import annotations

import logging

from app.schemas.memory.archive import MemoryImportReadiness
from app.services.agent.params.models import MigrationReadinessAnchorRequest
from app.services.agent.stream_session.entitlement_gap_preflight import (
    get_capability_gap_emission_tracker,
)
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from app.services.memory.operations.crud.import_readiness import (
    ImportReadinessStatus,
    pick_primary_readiness_issue,
    resolve_migration_readiness_gap_message,
    resolve_readiness_issue_action,
)

logger = logging.getLogger(__name__)

_MIGRATION_GAP_TOOL_ID = "migration_import"
_MIGRATION_READINESS_CRITICAL_REASON = "migration_readiness_critical"
_MIGRATION_READINESS_WARNING_REASON = "migration_readiness_warning"
_DEFAULT_MODELS_SETTINGS_PATH = "/settings/models"


def _extract_import_batch_id(
    anchor: MigrationReadinessAnchorRequest | dict[str, object],
) -> str:
    if isinstance(anchor, MigrationReadinessAnchorRequest):
        return anchor.import_batch_id.strip()
    raw_batch = anchor.get("importBatchId", anchor.get("import_batch_id"))
    return raw_batch.strip() if isinstance(raw_batch, str) else ""


def build_migration_readiness_gap_sse_event_from_readiness(
    *,
    message_id: str,
    import_batch_id: str,
    readiness: MemoryImportReadiness,
    chat_id: str | None,
    locale: str | None,
) -> dict[str, object] | None:
    """Emit capability_gap when live post-import readiness is warning or critical."""

    if readiness.status == "ready":
        return None

    reason = (
        _MIGRATION_READINESS_CRITICAL_REASON
        if readiness.status == "critical"
        else _MIGRATION_READINESS_WARNING_REASON
    )
    dedup_key = f"{_MIGRATION_GAP_TOOL_ID}:{reason}"
    tracker = get_capability_gap_emission_tracker()
    if not tracker.should_emit(chat_id, dedup_key):
        return None
    tracker.mark_emitted(chat_id, dedup_key)

    primary_issue = pick_primary_readiness_issue(readiness.issues)
    issue_code = primary_issue.code if primary_issue is not None else None
    issue_action = resolve_readiness_issue_action(issue_code or "")
    settings_path = (
        issue_action.settings_path
        if issue_action is not None
        else _DEFAULT_MODELS_SETTINGS_PATH
    )
    display_message = resolve_migration_readiness_gap_message(
        status=readiness.status,
        issue_code=issue_code,
        locale=locale,
    )

    data: dict[str, object] = {
        "tool_id": _MIGRATION_GAP_TOOL_ID,
        "tool_group": "migration",
        "reason": reason,
        "display_message": display_message,
        "settings_path": settings_path,
    }
    normalized_batch_id = import_batch_id.strip()
    if normalized_batch_id:
        data["import_batch_id"] = normalized_batch_id

    return {
        "type": "capability_gap",
        "messageId": message_id,
        "data": data,
    }


async def resolve_and_build_migration_readiness_gap_sse_event(
    *,
    message_id: str,
    migration_readiness_anchor: (
        MigrationReadinessAnchorRequest | dict[str, object] | None
    ),
    chat_id: str | None,
    locale: str | None,
) -> tuple[dict[str, object] | None, ImportReadinessStatus | None]:
    """Live-resolve migration readiness for anchor batch and optionally emit capability_gap."""

    if migration_readiness_anchor is None:
        return None, None

    import_batch_id = _extract_import_batch_id(migration_readiness_anchor)
    if not import_batch_id:
        return None, None

    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        try:
            readiness = await MemoryImportSessionService(
                db
            ).resolve_live_import_readiness(import_batch_id)
        except Exception as exc:
            logger.warning(
                "Failed to live-resolve migration readiness for batch %s: %s",
                import_batch_id,
                exc,
            )
            return None, None

    event = build_migration_readiness_gap_sse_event_from_readiness(
        message_id=message_id,
        import_batch_id=import_batch_id,
        readiness=readiness,
        chat_id=chat_id,
        locale=locale,
    )
    return event, readiness.status
