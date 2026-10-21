"""Kanban task list endpoint with stat badge & diagnostics enrichment.

[INPUT]
app.api.kanban.http_common::router/get_kanban_service/_batch_load_attachment_ids/_resolve_attachments/diag_engine (POS: Kanban API 共享路由与 DTO 装配)
app.api.kanban.schemas::TaskListResponse/TaskResponse/AttachmentInfo/DiagnosticSummaryResponse (POS: DTO)
app.services.kanban.diagnostics::CARD_FAST_RULES/compute_diagnostics_summary (POS: 诊断摘要)

[OUTPUT]
GET /boards/{board_id}/tasks endpoint registered on the shared kanban router.

[POS]
列表查询路由与其 DTO 富化装配；独立文件以控制模块行数。
"""

from __future__ import annotations

import asyncio

from fastapi import HTTPException, Query
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.api.kanban.http_common import (
    _batch_load_attachment_ids,
    _resolve_attachments,
    diag_engine,
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    AttachmentInfo,
    DiagnosticSummaryResponse,
    TaskListResponse,
    TaskResponse,
)
from app.core.kanban.adapters.sqlalchemy_store import TaskCardStats
from app.services.kanban.diagnostics import CARD_FAST_RULES, compute_diagnostics_summary


async def _task_to_response_with_stats(
    task: KanbanTask,
    *,
    att_map: dict[str, list[str]],
    resolved_map: dict[str, AttachmentInfo],
    stats: dict[str, TaskCardStats],
) -> TaskResponse:
    """Build a TaskResponse enriched with attachment, stat badges, and diagnostics."""
    att_ids = att_map.get(task.task_id, [])
    attachments = [resolved_map[fid] for fid in att_ids if fid in resolved_map]
    criteria = task.metadata.get("completion_criteria")
    resp = TaskResponse(
        task_id=task.task_id,
        board_id=task.board_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        agent_id=task.agent_id,
        model_override=task.model_override,
        parent_task_id=task.parent_task_id,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        consecutive_failures=task.consecutive_failures,
        blocked_reason=task.blocked_reason,
        block_kind=task.block_kind.value if task.block_kind else None,
        scheduled_until=task.scheduled_until,
        progress_note=task.progress_note,
        result=task.result,
        error=task.error,
        metadata=task.metadata,
        extra_skill_ids=task.extra_skill_ids,
        attachment_ids=att_ids,
        attachments=attachments,
        max_runtime_seconds=task.max_runtime_seconds,
        goal_mode=task.goal_mode,
        goal_max_turns=task.goal_max_turns,
        require_approval=task.require_approval,
        completion_criteria=criteria if isinstance(criteria, (str, list)) else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )
    stat = stats.get(task.task_id)
    if stat:
        resp.dep_count = stat.dep_count
        resp.children_total = stat.children_total
        resp.children_done = stat.children_done
        resp.comment_count = stat.comment_count
    diags = diag_engine.evaluate(task, rule_ids=CARD_FAST_RULES)
    summary = compute_diagnostics_summary(diags)
    if summary.count > 0:
        resp.diagnostics_summary = DiagnosticSummaryResponse(
            count=summary.count,
            max_severity=summary.max_severity,
        )
    return resp


@router.get("/boards/{board_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    board_id: str,
    status_filter: str | None = Query(None),
    agent_id: str | None = Query(None),
    source_chat_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TaskListResponse:
    svc = get_kanban_service()
    status: TaskStatus | None = None
    if status_filter:
        try:
            status = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status_filter}") from None

    tasks = await svc.list_tasks(
        board_id,
        status=status,
        agent_id=agent_id,
        source_chat_id=source_chat_id,
        limit=limit,
        offset=offset,
    )
    task_ids = [t.task_id for t in tasks]
    stats, att_map = await asyncio.gather(
        svc.store.batch_task_stats(task_ids),
        _batch_load_attachment_ids(task_ids),
    )

    all_file_ids = list({fid for ids in att_map.values() for fid in ids})
    all_resolved = await _resolve_attachments(all_file_ids)
    resolved_map: dict[str, AttachmentInfo] = {a.file_id: a for a in all_resolved}

    items = [
        await _task_to_response_with_stats(
            t,
            att_map=att_map,
            resolved_map=resolved_map,
            stats=stats,
        )
        for t in tasks
    ]
    return TaskListResponse(items=items, total=len(items))
