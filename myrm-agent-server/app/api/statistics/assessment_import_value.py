"""Assessment import post-import value anchor API.

[INPUT]
- app.database.models::AssessmentImportLedger (POS: immutable assessment import ledger)
- app.database.models::KanbanBoardModel/KanbanTaskModel (POS: imported task execution source)
- app.database.models::Milestone (POS: imported milestone execution state source)
- app.database.connection::get_db (POS: async DB session dependency)
- app.core.utils.response_utils::success_response (POS: standard API envelope)

[OUTPUT]
- GET /statistics/assessment-import/value-summary

[POS]
Post-import execution value summary: track task/milestone completion rates for
imports within a time window. Prefer `import_id` linkage, fallback to
`project_id + artifact_version_id` for legacy rows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import (
    AssessmentImportLedger,
    KanbanBoardModel,
    KanbanTaskModel,
    Milestone,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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
            str(board_id): str(board_project_id) for board_id, board_project_id in board_rows if board_id and board_project_id
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
                        completed_tasks_by_import_id[target_import_id] = completed_tasks_by_import_id.get(target_import_id, 0) + 1
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
                await db.execute(select(Milestone.id, Milestone.status).where(Milestone.id.in_(all_milestone_ids)))
            ).all()
            milestone_status_by_id = {
                str(milestone_id): str(status) for milestone_id, status in milestone_rows if milestone_id is not None
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
