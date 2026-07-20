"""Unified Runs Hub REST endpoint.

[INPUT]
- app.core.cron.manager::CronManager (POS: Cron 领域管理器)
- app.services.kanban::KanbanService (POS: Kanban task store)
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Background tasks)
- app.services.agent.shell_background_tasks (POS: Shell background tasks)

[OUTPUT]
- GET /runs — paginated unified run list (source filter, status filter)

[POS]
Read-only aggregation endpoint. Queries Cron runs, Kanban task runs, and Background
tasks in parallel, merges into a single sorted timeline. No write operations.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import cast

from fastapi import APIRouter, Query

from app.api.runs.schemas import (
    RunSource,
    RunStatus,
    UnifiedRunResponse,
    UnifiedRunsListResponse,
)

router = APIRouter(prefix="/runs", tags=["runs"])

USER_ID = "default"
_STOP_REASON_CATEGORIES = frozenset({"limit", "cancelled", "error", "other"})


def _safe_dt(dt: datetime | None, fallback: datetime | None = None) -> datetime:
    """Ensure a datetime is timezone-aware."""
    if dt is None:
        return fallback or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_stop_reason(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    code_obj = raw.get("code")
    if not isinstance(code_obj, str) or not code_obj.strip():
        return None
    code = code_obj.strip()
    category_obj = raw.get("category")
    category = category_obj if isinstance(category_obj, str) and category_obj in _STOP_REASON_CATEGORIES else "other"
    message_obj = raw.get("message")
    message = message_obj.strip() if isinstance(message_obj, str) and message_obj.strip() else code.replace("_", " ")
    normalized: dict[str, object] = {
        "code": code,
        "category": category,
        "message": message,
    }
    detail_obj = raw.get("detail")
    if isinstance(detail_obj, dict):
        normalized["detail"] = {str(k): v for k, v in detail_obj.items() if isinstance(k, str)}
    return normalized


def _extract_step_item_text(items: object) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _extract_stop_reason_from_metadata(metadata: dict[str, object] | None) -> dict[str, object] | None:
    if metadata is None:
        return None
    direct = _normalize_stop_reason(metadata.get("stopReason"))
    if direct is not None:
        return direct
    steps_obj = metadata.get("progressSteps")
    if not isinstance(steps_obj, list):
        return None
    for step_obj in reversed(steps_obj):
        if not isinstance(step_obj, dict):
            continue
        step_key = step_obj.get("step_key")
        if step_key == "iteration_limit_reached":
            message = "Iteration limit reached"
            step_text = _extract_step_item_text(step_obj.get("items"))
            if step_text:
                message = f"Iteration limit reached ({step_text})"
            return {
                "code": "iteration_limit_reached",
                "category": "limit",
                "message": message,
            }
    return None


def _stop_reason_from_error(error: str | None, status: RunStatus) -> dict[str, object] | None:
    if status == "timed_out":
        return {
            "code": "timed_out",
            "category": "limit",
            "message": error.strip() if isinstance(error, str) and error.strip() else "Execution timed out",
        }
    if status == "cancelled":
        return {
            "code": "user_cancelled",
            "category": "cancelled",
            "message": error.strip() if isinstance(error, str) and error.strip() else "Run cancelled",
        }
    if not error:
        return None
    error_text = error.strip()
    if not error_text:
        return None
    if "tool call limit exceeded" in error_text.lower() or "max_replan_attempts exceeded" in error_text.lower():
        return {
            "code": "engine_limit_reached",
            "category": "limit",
            "message": error_text,
        }
    return {
        "code": "error",
        "category": "error",
        "message": error_text,
    }


def _stop_reason_from_shell_task(task: object, status: RunStatus) -> dict[str, object] | None:
    if status in {"running", "ok"}:
        return None
    error_category_obj = getattr(task, "error_category", None)
    error_category = error_category_obj if isinstance(error_category_obj, str) and error_category_obj else None
    preview_obj = getattr(task, "result_preview", None)
    preview = preview_obj.strip() if isinstance(preview_obj, str) and preview_obj.strip() else None
    payload: dict[str, object]
    if status == "cancelled":
        payload = {
            "code": "user_cancelled",
            "category": "cancelled",
            "message": preview or "Shell task cancelled",
        }
    else:
        payload = {
            "code": "error",
            "category": "error",
            "message": preview or "Shell task failed",
        }
    if error_category is not None:
        payload["detail"] = {"error_category": error_category}
    return payload


async def _fetch_cron_runs(
    status_filter: RunStatus | None,
    limit: int,
) -> tuple[list[UnifiedRunResponse], bool]:
    """Fetch recent cron runs. Returns (items, available)."""
    from app.core.cron.adapters.setup import get_cron_manager

    mgr = get_cron_manager()
    if mgr is None:
        return [], False

    cron_status_map: dict[str, str] = {
        "ok": "ok",
        "error": "error",
        "skipped": "skipped",
    }

    if status_filter is not None and status_filter not in cron_status_map:
        # Historical cron runs only persist terminal statuses; non-matching filters yield no rows.
        return [], True

    filter_status = cron_status_map[status_filter] if status_filter else None

    runs = await mgr.list_runs(USER_ID, limit=limit, offset=0, status=filter_status)

    job_ids = list({r.job_id for r in runs})
    all_jobs = await mgr.list_jobs(USER_ID) if job_ids else []
    job_map = {j.id: j for j in all_jobs if j.id in set(job_ids)}

    results: list[UnifiedRunResponse] = []
    for r in runs:
        job = job_map.get(r.job_id)
        job_name = job.name if job else r.job_id
        agent_id = job.agent_id if job else None

        run_status: RunStatus = cast(RunStatus, r.status) if r.status in ("ok", "error", "skipped") else "error"
        metadata = r.metadata if isinstance(r.metadata, dict) else None
        has_execution_steps = bool(metadata and metadata.get("progressSteps"))
        stop_reason = _extract_stop_reason_from_metadata(metadata) or _stop_reason_from_error(r.error, run_status)

        results.append(
            UnifiedRunResponse(
                id=f"cron:{r.id}",
                source="cron",
                status=run_status,
                title=job_name,
                started_at=_safe_dt(r.started_at),
                finished_at=_safe_dt(r.finished_at),
                duration_ms=r.duration_ms,
                error=r.error,
                summary=_truncate(r.output, 200) if r.output else None,
                output=r.output,
                metadata=metadata,
                agent_id=agent_id,
                job_id=r.job_id,
                has_execution_steps=has_execution_steps,
                stop_reason=stop_reason,
            )
        )
    return results, True


async def _fetch_kanban_runs(
    status_filter: RunStatus | None,
    limit: int,
) -> tuple[list[UnifiedRunResponse], bool]:
    """Fetch recent kanban task runs from the __background_tasks__ board."""
    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    if svc is None:
        return [], False

    from app.core.channel_bridge.background_task_handler import _SYSTEM_BOARD_NAME

    boards = await svc.list_boards()
    board_id: str | None = None
    for board in boards:
        if board.name == _SYSTEM_BOARD_NAME:
            board_id = board.board_id
            break

    if board_id is None:
        # System board is created lazily on first background spawn; absence is not an outage.
        return [], True

    from myrm_agent_harness.toolkits.kanban.types import TaskStatus as KanbanStatus

    excluded = frozenset({KanbanStatus.ARCHIVED, KanbanStatus.TRIAGE})
    tasks = await svc.store.list_tasks(board_id, limit=limit)

    results: list[UnifiedRunResponse] = []
    for task in tasks:
        if task.status in excluded:
            continue
        task_status = _kanban_task_to_run_status(task.status.value, task.error)
        if status_filter and task_status != status_filter:
            continue

        started = _safe_dt(task.created_at)
        finished = _safe_dt(task.completed_at) if task.completed_at else None

        duration_ms: int | None = None
        if finished:
            duration_ms = int((finished - started).total_seconds() * 1000)
        stop_reason = _stop_reason_from_error(task.error, task_status)

        results.append(
            UnifiedRunResponse(
                id=f"kanban:{task.task_id}",
                source="kanban",
                status=task_status,
                title=task.title or task.description or "Background Task",
                started_at=started,
                finished_at=finished,
                duration_ms=duration_ms,
                error=task.error or None,
                summary=_truncate(task.description, 200) if task.description else None,
                agent_id=task.agent_id,
                task_id=task.task_id,
                stop_reason=stop_reason,
            )
        )
    return results, True


async def _fetch_background_shell_runs(
    status_filter: RunStatus | None,
) -> tuple[list[UnifiedRunResponse], bool]:
    """Fetch in-process shell background tasks."""
    from app.services.agent.shell_background_tasks import list_shell_background_tasks

    shell_tasks = list_shell_background_tasks()
    results: list[UnifiedRunResponse] = []

    for t in shell_tasks:
        task_status: RunStatus
        if t.status == "running":
            task_status = "running"
        elif t.status == "completed":
            task_status = "ok"
        elif t.status == "cancelled":
            task_status = "cancelled"
        else:
            task_status = "error"
        if status_filter and task_status != status_filter:
            continue

        started = datetime.fromtimestamp(t.created_at, tz=timezone.utc)
        finished = datetime.fromtimestamp(t.completed_at, tz=timezone.utc) if t.completed_at else None
        duration_ms: int | None = None
        if finished:
            duration_ms = int((finished - started).total_seconds() * 1000)
        stop_reason = _stop_reason_from_shell_task(t, task_status)

        results.append(
            UnifiedRunResponse(
                id=f"shell:{t.task_id}",
                source="background",
                status=task_status,
                title=_truncate(t.prompt, 80) or "Shell Task",
                started_at=started,
                finished_at=finished,
                duration_ms=duration_ms,
                summary=_truncate(t.result_preview, 200) if t.result_preview else None,
                stop_reason=stop_reason,
            )
        )
    return results, True


def _kanban_task_to_run_status(status: str, error: str | None) -> RunStatus:
    """Map kanban task status to unified run status."""
    error_lower = (error or "").lower()
    if status in ("triage", "backlog", "ready", "running"):
        return "running"
    if status == "blocked":
        if "timed out" in error_lower:
            return "timed_out"
        return "running"
    if status == "completed":
        return "ok"
    if status == "failed":
        if "timed out" in error_lower:
            return "timed_out"
        if "cancelled" in error_lower:
            return "cancelled"
        return "error"
    if status == "archived":
        return "cancelled"
    if error:
        return "error"
    return "ok"


def _truncate(text: str | None, max_len: int) -> str | None:
    if not text:
        return None
    return text[:max_len] + "..." if len(text) > max_len else text


@router.get("", response_model=UnifiedRunsListResponse)
async def list_unified_runs(
    source: RunSource | None = Query(None, description="Filter by source: cron, kanban, background"),
    status: RunStatus | None = Query(None, description="Filter by status"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> UnifiedRunsListResponse:
    """Aggregated run history from all execution sources."""
    fetch_limit = limit + offset + 10

    failed_sources: list[RunSource] = []
    all_runs: list[UnifiedRunResponse] = []

    async def collect_cron() -> None:
        try:
            items, available = await _fetch_cron_runs(status, fetch_limit)
            if not available:
                failed_sources.append("cron")
            all_runs.extend(items)
        except Exception:
            failed_sources.append("cron")

    async def collect_kanban() -> None:
        try:
            items, available = await _fetch_kanban_runs(status, fetch_limit)
            if not available:
                failed_sources.append("kanban")
            all_runs.extend(items)
        except Exception:
            failed_sources.append("kanban")

    async def collect_background() -> None:
        try:
            items, available = await _fetch_background_shell_runs(status)
            if not available:
                failed_sources.append("background")
            all_runs.extend(items)
        except Exception:
            failed_sources.append("background")

    collectors: list[asyncio.Task[None]] = []
    if source is None or source == "cron":
        collectors.append(asyncio.create_task(collect_cron()))
    if source is None or source == "kanban":
        collectors.append(asyncio.create_task(collect_kanban()))
    if source is None or source == "background":
        collectors.append(asyncio.create_task(collect_background()))

    if collectors:
        await asyncio.gather(*collectors)

    all_runs.sort(key=lambda r: r.started_at, reverse=True)

    total = len(all_runs)
    page = all_runs[offset : offset + limit]

    return UnifiedRunsListResponse(
        items=page,
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + limit < total,
        degraded=len(failed_sources) > 0,
        failed_sources=failed_sources,
    )
