"""Kanban task routes: CRUD, transitions, and attachment persistence.

[INPUT]
app.api.kanban.http_common::router/get_kanban_service (POS: Kanban API 共享路由与 DTO 装配)
app.api.kanban.routes.tasks_list::list_tasks (POS: 任务列表查询端点)
app.api.kanban.routes.skill_ids::validate_extra_skill_ids (POS: 任务技能 id 存在性校验)
app.services.kanban::KanbanService (POS: Kanban 业务编排)
app.services.kanban.task_attachment_ids::save_task_attachment_ids (POS: 任务附件 ID 持久化)

[OUTPUT]
Task-domain REST endpoints under /api/v1/kanban/tasks and /boards/{board_id}/tasks.

[POS]
Kanban Task 路由层。负责请求校验、错误映射和 service 调用装配，不承载业务编排。
"""

from __future__ import annotations

from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    TaskPriority,
    TaskStatus,
)

from app.api.kanban.http_common import (
    _task_response_with_attachments,
    get_kanban_service,
    router,
)
from app.api.kanban.routes.skill_ids import (
    validate_extra_skill_ids as _validate_extra_skill_ids,
)
from app.api.kanban.schemas import (
    ApproveTaskRequest,
    PromoteRequest,
    PromoteResponse,
    ReclaimRequest,
    ReclaimResponse,
    RejectTaskRequest,
    TaskCreate,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdate,
    UnmetParent,
)
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.channel_bridge.model_resolver import validate_model_override
from app.services.kanban import DependencyUnmetError
from app.services.kanban.task_attachment_ids import save_task_attachment_ids as _save_task_attachment_ids

# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------


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

    model_override: str | None = None
    if body.model_override:
        user_cfgs = await load_user_configs()
        err = validate_model_override(user_cfgs.providers_dict, body.model_override)
        if err:
            raise HTTPException(400, err)
        model_override = body.model_override

    if body.extra_skill_ids:
        await _validate_extra_skill_ids(body.extra_skill_ids)

    try:
        task = await svc.add_task(
            board_id=board_id,
            title=body.title,
            description=body.description,
            priority=priority,
            parent_task_id=body.parent_task_id,
            agent_id=body.agent_id,
            model_override=model_override,
            max_retries=body.max_retries,
            depends_on=body.depends_on or None,
            extra_skill_ids=body.extra_skill_ids or None,
            completion_criteria=body.completion_criteria,
            initial_status=initial_status,
            max_runtime_seconds=body.max_runtime_seconds,
            workspace_path=body.workspace_path,
            branch=body.branch,
            goal_mode=body.goal_mode,
            goal_max_turns=body.goal_max_turns,
            require_approval=body.require_approval,
            metadata_patch=body.metadata,
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
        if "model_override" in body.model_fields_set:
            value = body.model_override
            if value:
                user_cfgs = await load_user_configs()
                err = validate_model_override(user_cfgs.providers_dict, value)
                if err:
                    raise HTTPException(400, err)
            kwargs["model_override"] = value or None
        if "extra_skill_ids" in body.model_fields_set:
            if body.extra_skill_ids:
                await _validate_extra_skill_ids(body.extra_skill_ids)
            kwargs["extra_skill_ids"] = body.extra_skill_ids
        if "max_runtime_seconds" in body.model_fields_set:
            kwargs["max_runtime_seconds"] = body.max_runtime_seconds
        if body.result is not None:
            kwargs["result"] = body.result
        if body.metadata is not None:
            kwargs["metadata"] = body.metadata
        if "require_approval" in body.model_fields_set:
            kwargs["require_approval"] = body.require_approval
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


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
async def approve_task(task_id: str, body: ApproveTaskRequest) -> TaskResponse:
    """Approve an IN_REVIEW task — marks it completed and releases dependents."""
    svc = get_kanban_service()
    try:
        task = await svc.approve_task(task_id, approver=body.approver)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return await _task_response_with_attachments(task)


@router.post("/tasks/{task_id}/reject", response_model=TaskResponse)
async def reject_task(task_id: str, body: RejectTaskRequest) -> TaskResponse:
    """Reject an IN_REVIEW task — sends it back to READY for rework."""
    svc = get_kanban_service()
    try:
        task = await svc.reject_task(task_id, reason=body.reason, approver=body.approver)
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
        unmet_parents=[UnmetParent(**p) for p in result.unmet_parents],
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
