"""Kanban API routes — tasks."""

from __future__ import annotations

from fastapi import HTTPException, Query
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    TaskPriority,
    TaskStatus,
)

from app.api.kanban.http_common import (
    _batch_load_attachment_ids,
    _resolve_attachments,
    _save_task_attachment_ids,
    _task_response_with_attachments,
    diag_engine,
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    AttachmentInfo,
    DiagnosticSummaryResponse,
    PromoteRequest,
    PromoteResponse,
    ReclaimRequest,
    ReclaimResponse,
    TaskCreate,
    TaskListResponse,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdate,
)
from app.services.kanban import DependencyUnmetError
from app.services.kanban.diagnostics import (
    CARD_FAST_RULES,
    compute_diagnostics_summary,
)

# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}/tasks", response_model=TaskListResponse)
async def list_tasks(
    board_id: str,
    status_filter: str | None = Query(None),
    agent_id: str | None = Query(None),
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

    tasks = await svc.list_tasks(board_id, status=status, agent_id=agent_id, limit=limit, offset=offset)
    task_ids = [t.task_id for t in tasks]
    stats, att_map = await svc.store.batch_task_stats(task_ids), await _batch_load_attachment_ids(task_ids)

    all_file_ids = list({fid for ids in att_map.values() for fid in ids})
    all_resolved = await _resolve_attachments(all_file_ids)
    resolved_map: dict[str, AttachmentInfo] = {a.file_id: a for a in all_resolved}

    items: list[TaskResponse] = []
    for t in tasks:
        att_ids = att_map.get(t.task_id, [])
        attachments = [resolved_map[fid] for fid in att_ids if fid in resolved_map]
        criteria = t.metadata.get("completion_criteria")
        resp = TaskResponse(
            task_id=t.task_id,
            board_id=t.board_id,
            title=t.title,
            description=t.description,
            status=t.status.value,
            priority=t.priority.value,
            agent_id=t.agent_id,
            goal_id=t.goal_id,
            parent_task_id=t.parent_task_id,
            retry_count=t.retry_count,
            max_retries=t.max_retries,
            consecutive_failures=t.consecutive_failures,
            blocked_reason=t.blocked_reason,
            block_kind=t.block_kind.value if t.block_kind else None,
            scheduled_until=t.scheduled_until,
            progress_note=t.progress_note,
            result=t.result,
            error=t.error,
            metadata=t.metadata,
            extra_skill_ids=t.extra_skill_ids,
            attachment_ids=att_ids,
            attachments=attachments,
            max_runtime_seconds=t.max_runtime_seconds,
            completion_criteria=criteria if isinstance(criteria, (str, list)) else None,
            created_at=t.created_at,
            updated_at=t.updated_at,
            completed_at=t.completed_at,
        )
        s = stats.get(t.task_id)
        if s:
            resp.dep_count = s.dep_count
            resp.children_total = s.children_total
            resp.children_done = s.children_done
            resp.comment_count = s.comment_count
        diags = diag_engine.evaluate(t, rule_ids=CARD_FAST_RULES)
        summary = compute_diagnostics_summary(diags)
        if summary.count > 0:
            resp.diagnostics_summary = DiagnosticSummaryResponse(
                count=summary.count,
                max_severity=summary.max_severity,
            )
        items.append(resp)
    return TaskListResponse(items=items, total=len(items))


@router.post("/boards/{board_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(board_id: str, body: TaskCreate) -> TaskResponse:
    svc = get_kanban_service()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")

    try:
        priority = TaskPriority(body.priority)
    except ValueError:
        priority = TaskPriority.NORMAL

    initial_status: TaskStatus | None = None
    if body.initial_status:
        try:
            initial_status = TaskStatus(body.initial_status)
        except ValueError:
            raise HTTPException(
                400,
                f"Invalid initial_status: {body.initial_status}",
            ) from None

    try:
        task = await svc.add_task(
            board_id=board_id,
            title=body.title,
            description=body.description,
            priority=priority,
            parent_task_id=body.parent_task_id,
            agent_id=body.agent_id,
            max_retries=body.max_retries,
            depends_on=body.depends_on or None,
            extra_skill_ids=body.extra_skill_ids or None,
            completion_criteria=body.completion_criteria,
            initial_status=initial_status,
            max_runtime_seconds=body.max_runtime_seconds,
            workspace_path=body.workspace_path,
            branch=body.branch,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if body.attachment_ids:
        await _save_task_attachment_ids(task.task_id, body.attachment_ids)

    if task.status == TaskStatus.TRIAGE and board.settings.auto_specify_on_create:
        outcome = await svc.specify_task(task.task_id, persist=True)
        if outcome.ok and outcome.persisted:
            refreshed = await svc.get_task(task.task_id)
            if refreshed is not None:
                task = refreshed
    return await _task_response_with_attachments(task)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return await _task_response_with_attachments(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, body: TaskUpdate) -> TaskResponse:
    svc = get_kanban_service()
    priority: TaskPriority | None = None
    if body.priority:
        try:
            priority = TaskPriority(body.priority)
        except ValueError:
            pass

    try:
        kwargs: dict[str, object] = {
            "title": body.title,
            "description": body.description,
            "priority": priority,
            "completion_criteria": body.completion_criteria,
        }
        if "agent_id" in body.model_fields_set:
            kwargs["agent_id"] = body.agent_id
        if "extra_skill_ids" in body.model_fields_set:
            kwargs["extra_skill_ids"] = body.extra_skill_ids
        if "max_runtime_seconds" in body.model_fields_set:
            kwargs["max_runtime_seconds"] = body.max_runtime_seconds
        if body.result is not None:
            kwargs["result"] = body.result
        if body.metadata is not None:
            kwargs["metadata"] = body.metadata
        task = await svc.update_task(task_id, **kwargs)  # type: ignore[arg-type]
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")

    if "attachment_ids" in body.model_fields_set:
        await _save_task_attachment_ids(task_id, body.attachment_ids or [])

    return await _task_response_with_attachments(task)


@router.post("/tasks/{task_id}/move", response_model=TaskResponse)
async def move_task(task_id: str, body: TaskMoveRequest) -> TaskResponse:
    try:
        target_status = TaskStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}") from None

    svc = get_kanban_service()
    try:
        block_kind: BlockKind | None = None
        if body.block_kind:
            try:
                block_kind = BlockKind(body.block_kind)
            except ValueError:
                raise HTTPException(400, f"Invalid block_kind: {body.block_kind}") from None
        task = await svc.move_task(
            task_id,
            target_status,
            force=body.force,
            block_kind=block_kind,
            blocked_reason=body.blocked_reason,
            scheduled_until=body.scheduled_until,
            result=body.result,
            metadata=body.metadata,
        )
    except DependencyUnmetError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "deps_unmet",
                "unsatisfied": exc.unsatisfied,
                "unmet_parents": list(exc.unmet_details),
                "message": str(exc),
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return await _task_response_with_attachments(task)


@router.post("/tasks/{task_id}/promote", response_model=PromoteResponse)
async def promote_task(task_id: str, body: PromoteRequest) -> PromoteResponse:
    svc = get_kanban_service()
    try:
        result = await svc.promote_task(task_id, force=body.force, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return PromoteResponse(
        promoted=result.promoted,
        forced=result.forced,
        reason=result.reason,
        unmet_parents=[{"task_id": p["task_id"], "title": p["title"], "status": p["status"]} for p in result.unmet_parents],
    )


@router.post("/tasks/{task_id}/reclaim", response_model=ReclaimResponse)
async def reclaim_task(task_id: str, body: ReclaimRequest) -> ReclaimResponse:
    svc = get_kanban_service()
    try:
        task = await svc.reclaim_task(
            task_id,
            reason=body.reason,
            new_agent_id=body.new_agent_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return ReclaimResponse(reclaimed=True, task=await _task_response_with_attachments(task))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str) -> None:
    svc = get_kanban_service()
    deleted = await svc.delete_task(task_id)
    if not deleted:
        raise HTTPException(404, f"Task {task_id} not found")
