"""Assessment import funnel observability API.

[INPUT]
- app.database.models::AssessmentImportMetricEvent (POS: observability event ORM model)
- app.database.models::AssessmentImportLedger (POS: immutable assessment import ledger)
- app.database.models::KanbanBoardModel/KanbanTaskModel (POS: imported task execution source)
- app.database.models::Milestone (POS: imported milestone execution state source)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- POST /statistics/assessment-import/events
- GET /statistics/assessment-import/summary
- GET /statistics/assessment-import/value-summary

[POS]
Collect and aggregate assessment import funnel events:
attempt/success/failure + failure reason + entry trigger mix,
and post-import value anchors based on task/milestone completion
(prefer `import_id` linkage, fallback to `project_id + artifact_version_id` for legacy rows).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import (
    AssessmentImportLedger,
    AssessmentImportMetricEvent,
    KanbanBoardModel,
    KanbanTaskModel,
    Milestone,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_SURFACES = ("project_milestone_panel",)
_TRIGGERS = ("manual_input", "recent_candidate")
_RETENTION_DAYS = 90
_CLEANUP_MIN_INTERVAL = timedelta(hours=6)
_cleanup_lock = asyncio.Lock()
_last_cleanup_at: datetime | None = None

AssessmentImportFailureReason = Literal[
    "artifact_version_already_imported",
    "no_actionable_tasks",
    "no_importable_tasks",
    "artifact_not_found",
    "project_not_found",
    "network_error",
    "unknown_error",
]


class AssessmentImportEventRequest(BaseModel):
    event_type: Literal[
        "import_attempted",
        "import_succeeded",
        "import_failed",
        "dropped_report",
    ]
    surface: Literal["project_milestone_panel"]
    trigger: Literal["manual_input", "recent_candidate"]
    context_key: str | None = Field(default=None, min_length=1, max_length=128)
    failure_reason: AssessmentImportFailureReason | None = None
    count: int = Field(default=1, ge=1, le=200)


class AssessmentImportSummaryResponse(BaseModel):
    days: int
    retention_days: int
    total_events: int
    import_attempted_count: int
    import_succeeded_count: int
    import_failed_count: int
    dropped_event_count: int
    success_rate: float
    failure_rate: float
    recent_candidate_attempt_rate: float
    attempts_by_trigger: dict[str, int]
    successes_by_trigger: dict[str, int]
    failures_by_trigger: dict[str, int]
    failure_reason_breakdown: dict[str, int]


class AssessmentImportValueSummaryResponse(BaseModel):
    days: int
    project_id: str | None
    imports_total: int
    imports_with_task_completion: int
    imports_with_milestone_completion: int
    imported_tasks_total: int
    completed_tasks_total: int
    imported_milestones_total: int
    completed_milestones_total: int
    task_completion_rate: float
    milestone_completion_rate: float
    import_activation_rate: float


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _normalize_context_key(context_key: str | None) -> str | None:
    normalized = context_key.strip() if context_key else ""
    return normalized or None


def _normalize_failure_reason(
    event_type: str,
    failure_reason: AssessmentImportFailureReason | None,
) -> AssessmentImportFailureReason | None:
    if event_type == "import_failed":
        return failure_reason or "unknown_error"
    if failure_reason is not None:
        raise validation_error("failure_reason is only valid for import_failed")
    return None


def _validate_metric_fields(payload: AssessmentImportEventRequest) -> None:
    if payload.event_type != "dropped_report" and payload.count != 1:
        raise validation_error("count must be 1 except for dropped_report")


def _extract_import_identity(metadata: object) -> tuple[int | None, str, str, str | None] | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("assessment_import")
    if not isinstance(raw, dict):
        return None
    project_id = raw.get("project_id")
    artifact_version_id = raw.get("artifact_version_id")
    if not isinstance(project_id, str) or not project_id.strip():
        return None
    if not isinstance(artifact_version_id, str) or not artifact_version_id.strip():
        return None
    raw_import_id = raw.get("import_id")
    normalized_import_id: int | None = None
    if isinstance(raw_import_id, int) and not isinstance(raw_import_id, bool) and raw_import_id > 0:
        normalized_import_id = raw_import_id
    elif isinstance(raw_import_id, str):
        normalized_text = raw_import_id.strip()
        if normalized_text.isdigit():
            parsed_import_id = int(normalized_text)
            if parsed_import_id > 0:
                normalized_import_id = parsed_import_id
    milestone_id = raw.get("milestone_id")
    normalized_milestone_id = milestone_id.strip() if isinstance(milestone_id, str) and milestone_id.strip() else None
    return normalized_import_id, project_id.strip(), artifact_version_id.strip(), normalized_milestone_id


async def _maybe_prune_old_events(db: AsyncSession) -> int:
    """Best-effort periodic cleanup for old assessment import events."""
    global _last_cleanup_at

    now = datetime.now(timezone.utc)
    if _last_cleanup_at is not None and now - _last_cleanup_at < _CLEANUP_MIN_INTERVAL:
        return 0

    async with _cleanup_lock:
        now = datetime.now(timezone.utc)
        if _last_cleanup_at is not None and now - _last_cleanup_at < _CLEANUP_MIN_INTERVAL:
            return 0

        cutoff = now - timedelta(days=_RETENTION_DAYS)
        prune_stmt = (
            delete(AssessmentImportMetricEvent)
            .where(AssessmentImportMetricEvent.created_at < cutoff)
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(prune_stmt)
        await db.commit()
        _last_cleanup_at = now
        return int(result.rowcount or 0)


async def _sum_event_count(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> int:
    stmt = select(func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0)).where(
        and_(
            AssessmentImportMetricEvent.created_at >= start_dt,
            AssessmentImportMetricEvent.event_type == event_type,
        )
    )
    return int((await db.execute(stmt)).scalar() or 0)


async def _trigger_breakdown(
    db: AsyncSession,
    start_dt: datetime,
    event_type: str,
) -> dict[str, int]:
    stmt = (
        select(
            AssessmentImportMetricEvent.trigger,
            func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0),
        )
        .where(
            and_(
                AssessmentImportMetricEvent.created_at >= start_dt,
                AssessmentImportMetricEvent.event_type == event_type,
            )
        )
        .group_by(AssessmentImportMetricEvent.trigger)
    )
    rows = (await db.execute(stmt)).all()
    breakdown = {trigger: 0 for trigger in _TRIGGERS}
    for trigger, total in rows:
        key = str(trigger)
        if key in breakdown:
            breakdown[key] = int(total or 0)
    return breakdown


async def _failure_reason_breakdown(
    db: AsyncSession,
    start_dt: datetime,
) -> dict[str, int]:
    stmt = (
        select(
            AssessmentImportMetricEvent.failure_reason,
            func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0),
        )
        .where(
            and_(
                AssessmentImportMetricEvent.created_at >= start_dt,
                AssessmentImportMetricEvent.event_type == "import_failed",
                AssessmentImportMetricEvent.failure_reason.isnot(None),
            )
        )
        .group_by(AssessmentImportMetricEvent.failure_reason)
    )
    rows = (await db.execute(stmt)).all()
    return {str(reason): int(total or 0) for reason, total in rows if reason}


@router.post("/assessment-import/events", response_model=None)
async def record_assessment_import_event(
    payload: AssessmentImportEventRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Record one assessment import funnel event."""
    try:
        _validate_metric_fields(payload)
        failure_reason = _normalize_failure_reason(payload.event_type, payload.failure_reason)
        event = AssessmentImportMetricEvent(
            event_type=payload.event_type,
            surface=payload.surface,
            trigger=payload.trigger,
            context_key=_normalize_context_key(payload.context_key),
            failure_reason=failure_reason,
            count=payload.count,
        )
        db.add(event)
        await db.commit()
        await _maybe_prune_old_events(db)
        return success_response(data={"accepted": True})
    except Exception as exc:
        if getattr(exc, "status_code", None) == 400:
            raise
        logger.exception("Assessment import metric ingest failed")
        raise internal_error(operation="Record assessment import event", exception=exc) from exc


@router.get("/assessment-import/summary")
async def get_assessment_import_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return assessment import funnel summary."""
    try:
        await _maybe_prune_old_events(db)
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)

        total_stmt = select(func.coalesce(func.sum(AssessmentImportMetricEvent.count), 0)).where(
            AssessmentImportMetricEvent.created_at >= start_dt
        )
        total_events = int((await db.execute(total_stmt)).scalar() or 0)

        attempted_count = await _sum_event_count(db, start_dt, "import_attempted")
        succeeded_count = await _sum_event_count(db, start_dt, "import_succeeded")
        failed_count = await _sum_event_count(db, start_dt, "import_failed")
        dropped_count = await _sum_event_count(db, start_dt, "dropped_report")

        attempts_by_trigger = await _trigger_breakdown(db, start_dt, "import_attempted")
        successes_by_trigger = await _trigger_breakdown(db, start_dt, "import_succeeded")
        failures_by_trigger = await _trigger_breakdown(db, start_dt, "import_failed")
        failure_reason_breakdown = await _failure_reason_breakdown(db, start_dt)

        summary = AssessmentImportSummaryResponse(
            days=days,
            retention_days=_RETENTION_DAYS,
            total_events=total_events,
            import_attempted_count=attempted_count,
            import_succeeded_count=succeeded_count,
            import_failed_count=failed_count,
            dropped_event_count=dropped_count,
            success_rate=_safe_rate(succeeded_count, attempted_count),
            failure_rate=_safe_rate(failed_count, attempted_count),
            recent_candidate_attempt_rate=_safe_rate(
                attempts_by_trigger.get("recent_candidate", 0),
                attempted_count,
            ),
            attempts_by_trigger=attempts_by_trigger,
            successes_by_trigger=successes_by_trigger,
            failures_by_trigger=failures_by_trigger,
            failure_reason_breakdown=failure_reason_breakdown,
        )
        return success_response(data=summary.model_dump(mode="json"))
    except Exception as exc:
        if getattr(exc, "status_code", None) == 400:
            raise
        logger.exception("Assessment import summary failed")
        raise internal_error(operation="Get assessment import summary", exception=exc) from exc


@router.get("/assessment-import/value-summary")
async def get_assessment_import_value_summary(
    days: int = Query(30, ge=1, le=90),
    project_id: str | None = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return post-import execution value summary (tasks/milestones completion)."""
    try:
        start_dt = datetime.now(timezone.utc) - timedelta(days=days)
        normalized_project_id = project_id.strip() if project_id else None

        ledger_stmt = select(AssessmentImportLedger).where(
            and_(
                AssessmentImportLedger.status == "completed",
                AssessmentImportLedger.created_at >= start_dt,
            )
        )
        if normalized_project_id:
            ledger_stmt = ledger_stmt.where(AssessmentImportLedger.project_id == normalized_project_id)

        ledgers = (await db.execute(ledger_stmt)).scalars().all()
        if not ledgers:
            empty_summary = AssessmentImportValueSummaryResponse(
                days=days,
                project_id=normalized_project_id,
                imports_total=0,
                imports_with_task_completion=0,
                imports_with_milestone_completion=0,
                imported_tasks_total=0,
                completed_tasks_total=0,
                imported_milestones_total=0,
                completed_milestones_total=0,
                task_completion_rate=0.0,
                milestone_completion_rate=0.0,
                import_activation_rate=0.0,
            )
            return success_response(data=empty_summary.model_dump(mode="json"))

        ledger_ids = {int(ledger.id) for ledger in ledgers}
        ledger_keys = {(str(ledger.project_id), str(ledger.artifact_version_id)) for ledger in ledgers}
        candidate_project_ids = sorted({str(ledger.project_id) for ledger in ledgers})
        board_stmt = select(KanbanBoardModel.id, KanbanBoardModel.project_id).where(
            KanbanBoardModel.project_id.in_(candidate_project_ids)
        )
        board_rows = (await db.execute(board_stmt)).all()
        board_project_map = {
            str(board_id): str(board_project_id)
            for board_id, board_project_id in board_rows
            if board_id and board_project_id
        }
        board_ids = list(board_project_map.keys())

        completed_tasks_by_import_id: dict[int, int] = {}
        completed_tasks_by_key: dict[tuple[str, str], int] = {}
        milestone_ids_by_import_id: dict[int, set[str]] = {}
        milestone_ids_by_key: dict[tuple[str, str], set[str]] = {}
        if board_ids:
            task_stmt = select(
                KanbanTaskModel.board_id,
                KanbanTaskModel.status,
                KanbanTaskModel.metadata_json,
            ).where(
                and_(
                    KanbanTaskModel.board_id.in_(board_ids),
                    KanbanTaskModel.metadata_json.isnot(None),
                )
            )
            task_rows = (await db.execute(task_stmt)).all()
            for board_id, status, metadata in task_rows:
                import_identity = _extract_import_identity(metadata)
                if import_identity is None:
                    continue
                import_id, metadata_project_id, artifact_version_id, milestone_id = import_identity
                board_project_id = board_project_map.get(str(board_id))
                if board_project_id is None or metadata_project_id != board_project_id:
                    continue
                key = (metadata_project_id, artifact_version_id)
                target_import_id = import_id if import_id in ledger_ids else None
                if target_import_id is None and key not in ledger_keys:
                    continue
                if str(status) == "completed":
                    if target_import_id is not None:
                        completed_tasks_by_import_id[target_import_id] = (
                            completed_tasks_by_import_id.get(target_import_id, 0) + 1
                        )
                    else:
                        completed_tasks_by_key[key] = completed_tasks_by_key.get(key, 0) + 1
                if milestone_id is not None:
                    if target_import_id is not None:
                        milestone_ids_by_import_id.setdefault(target_import_id, set()).add(milestone_id)
                    else:
                        milestone_ids_by_key.setdefault(key, set()).add(milestone_id)

        milestone_status_by_id: dict[str, str] = {}
        all_milestone_ids = sorted(
            {
                milestone_id
                for ids in [*milestone_ids_by_import_id.values(), *milestone_ids_by_key.values()]
                for milestone_id in ids
            }
        )
        if all_milestone_ids:
            milestone_rows = (
                await db.execute(
                    select(Milestone.id, Milestone.status).where(Milestone.id.in_(all_milestone_ids))
                )
            ).all()
            milestone_status_by_id = {
                str(milestone_id): str(status)
                for milestone_id, status in milestone_rows
                if milestone_id is not None
            }

        imports_total = len(ledgers)
        imports_with_task_completion = 0
        imports_with_milestone_completion = 0
        imported_tasks_total = 0
        completed_tasks_total = 0
        imported_milestones_total = 0
        completed_milestones_total = 0

        for ledger in ledgers:
            ledger_id = int(ledger.id)
            key = (str(ledger.project_id), str(ledger.artifact_version_id))
            imported_tasks_total += int(ledger.total_tasks or 0)
            imported_milestones_total += int(ledger.total_milestones or 0)

            completed_tasks = completed_tasks_by_import_id.get(ledger_id)
            if completed_tasks is None:
                completed_tasks = completed_tasks_by_key.get(key, 0)
            completed_tasks_total += completed_tasks
            if completed_tasks > 0:
                imports_with_task_completion += 1

            milestone_ids = milestone_ids_by_import_id.get(ledger_id)
            if milestone_ids is None:
                milestone_ids = milestone_ids_by_key.get(key, set())
            completed_milestones = sum(
                1 for milestone_id in milestone_ids if milestone_status_by_id.get(milestone_id) == "completed"
            )
            completed_milestones_total += completed_milestones
            if completed_milestones > 0:
                imports_with_milestone_completion += 1

        summary = AssessmentImportValueSummaryResponse(
            days=days,
            project_id=normalized_project_id,
            imports_total=imports_total,
            imports_with_task_completion=imports_with_task_completion,
            imports_with_milestone_completion=imports_with_milestone_completion,
            imported_tasks_total=imported_tasks_total,
            completed_tasks_total=completed_tasks_total,
            imported_milestones_total=imported_milestones_total,
            completed_milestones_total=completed_milestones_total,
            task_completion_rate=_safe_rate(
                min(completed_tasks_total, imported_tasks_total),
                imported_tasks_total,
            ),
            milestone_completion_rate=_safe_rate(
                min(completed_milestones_total, imported_milestones_total),
                imported_milestones_total,
            ),
            import_activation_rate=_safe_rate(
                imports_with_task_completion,
                imports_total,
            ),
        )
        return success_response(data=summary.model_dump(mode="json"))
    except Exception as exc:
        if getattr(exc, "status_code", None) == 400:
            raise
        logger.exception("Assessment import value summary failed")
        raise internal_error(operation="Get assessment import value summary", exception=exc) from exc
