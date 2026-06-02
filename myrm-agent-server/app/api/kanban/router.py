"""Kanban REST API endpoints.

Thin delegation layer: parameter parsing -> KanbanService -> response conversion.

[INPUT]
- services.kanban::KanbanService (POS: Kanban business orchestration.)
- .schemas (POS: Pydantic request/response models.)

[OUTPUT]
- Board CRUD: GET/POST/DELETE /boards
- Task CRUD: GET/POST/PATCH/DELETE /boards/{board_id}/tasks
- Task actions: POST /tasks/{task_id}/move, POST /tasks/{task_id}/promote, POST /tasks/{task_id}/reclaim
- Task runs: GET /tasks/{task_id}/runs
- Task events: GET /tasks/{task_id}/events
- Task comments: POST /tasks/{task_id}/comments
- Task dependencies: GET/POST/DELETE /tasks/{task_id}/dependencies
- Task dependents: GET /tasks/{task_id}/dependents
- Task diagnostics: GET /tasks/{task_id}/diagnostics
- Board summary: GET /boards/{board_id}/summary
- Attachment resolution: _resolve_attachments() -> AttachmentInfo list with metadata + URL

[POS]
Kanban REST API endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from myrm_agent_harness.toolkits.kanban.types import (
    BlockKind,
    KanbanBoard,
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.api.kanban.schemas import (
    AgentTaskCounts,
    ApplyDecomposeRequest,
    ApplySpecRequest,
    AttachmentInfo,
    BoardCreate,
    BoardEventListResponse,
    BoardEventResponse,
    BoardListResponse,
    BoardResponse,
    BoardSummaryResponse,
    BoardUpdate,
    BulkActionItemResult,
    BulkActionRequest,
    BulkActionResponse,
    CommentCreate,
    DecomposeChildResponse,
    DecomposeOutcomeResponse,
    DependencyListResponse,
    DependencyRequest,
    DependencyResponse,
    DiagnosticActionResponse,
    DiagnosticSummaryResponse,
    EdgeListResponse,
    EventListResponse,
    EventResponse,
    PromoteRequest,
    PromoteResponse,
    ReclaimRequest,
    ReclaimResponse,
    RunListResponse,
    RunResponse,
    SpecifyAllResponse,
    SpecifyOutcomeResponse,
    TaskCreate,
    TaskDiagnosticResponse,
    TaskDiagnosticsResponse,
    TaskListResponse,
    TaskMoveRequest,
    TaskResponse,
    TaskUpdate,
)
from app.core.kanban.adapters.sqlalchemy_mapping import (
    get_attachment_ids,
    set_attachment_ids,
)
from app.services.kanban import DependencyUnmetError, KanbanService
from app.services.kanban.diagnostics import (
    CARD_FAST_RULES,
    compute_diagnostics_summary,
    create_diagnostic_engine,
)

router = APIRouter(prefix="/kanban", tags=["kanban"])

_diag_engine = create_diagnostic_engine()


def _svc() -> KanbanService:
    return KanbanService.get_instance()


async def _load_task_attachment_ids(task_id: str) -> list[str]:
    """Load attachment IDs from the DB for a task."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        m = await session.get(KanbanTaskModel, task_id)
        return get_attachment_ids(m) if m else []


async def _batch_load_attachment_ids(task_ids: list[str]) -> dict[str, list[str]]:
    """Batch-load attachment IDs for multiple tasks (avoids N+1)."""
    if not task_ids:
        return {}
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        stmt = select(
            KanbanTaskModel.id, KanbanTaskModel.attachment_ids_json,
        ).where(
            KanbanTaskModel.id.in_(task_ids),
            KanbanTaskModel.attachment_ids_json.is_not(None),
        )
        rows = (await session.execute(stmt)).all()
        return {r[0]: list(r[1]) for r in rows if r[1]}


async def _save_task_attachment_ids(task_id: str, ids: list[str]) -> None:
    """Persist attachment IDs on a task row."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        m = await session.get(KanbanTaskModel, task_id)
        if m:
            set_attachment_ids(m, ids)
            await session.commit()


async def _task_response_with_attachments(task: KanbanTask) -> TaskResponse:
    """Build a TaskResponse with attachment info resolved from DB."""
    att_ids = await _load_task_attachment_ids(task.task_id)
    return await _task_to_response(task, attachment_ids=att_ids)


def _board_to_response(board: KanbanBoard) -> BoardResponse:
    return BoardResponse(
        board_id=board.board_id,
        name=board.name,
        description=board.description,
        settings={
            "max_concurrent_tasks": board.settings.max_concurrent_tasks,
            "heartbeat_interval_seconds": board.settings.heartbeat_interval_seconds,
            "zombie_timeout_seconds": board.settings.zombie_timeout_seconds,
            "max_retries_per_task": board.settings.max_retries_per_task,
            "auto_block_after_consecutive_failures": board.settings.auto_block_after_consecutive_failures,
            "specify_max_tokens": board.settings.specify_max_tokens,
            "auto_specify_on_create": board.settings.auto_specify_on_create,
            "default_workdir": board.settings.default_workdir,
        },
        created_at=board.created_at,
        updated_at=board.updated_at,
    )


async def _resolve_attachments(ids: list[str]) -> list[AttachmentInfo]:
    """Resolve file IDs to attachment metadata for display (concurrent)."""
    if not ids:
        return []
    import asyncio

    from app.core.storage import files_service

    async def _resolve_one(fid: str) -> AttachmentInfo:
        url = f"/api/v1/files/{fid}/content"
        filename = fid
        content_type = "application/octet-stream"
        try:
            info = await files_service.get_file(fid)
            if info:
                filename = getattr(info, "filename", fid)
                content_type = getattr(info, "content_type", content_type)
        except Exception:
            pass
        return AttachmentInfo(
            file_id=fid, filename=filename,
            content_type=content_type, url=url,
        )

    return list(await asyncio.gather(*(_resolve_one(fid) for fid in ids)))


async def _task_to_response(
    task: KanbanTask,
    *,
    attachment_ids: list[str] | None = None,
) -> TaskResponse:
    ids = attachment_ids or []
    attachments = await _resolve_attachments(ids)
    criteria = task.metadata.get("completion_criteria")
    return TaskResponse(
        task_id=task.task_id,
        board_id=task.board_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        agent_id=task.agent_id,
        goal_id=task.goal_id,
        parent_task_id=task.parent_task_id,
        workspace_path=task.workspace_path,
        branch=task.branch,
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
        attachment_ids=ids,
        attachments=attachments,
        max_runtime_seconds=task.max_runtime_seconds,
        completion_criteria=criteria if isinstance(criteria, str) else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )


# ---------------------------------------------------------------------------
# Board endpoints
# ---------------------------------------------------------------------------


@router.get("/boards", response_model=BoardListResponse)
async def list_boards() -> BoardListResponse:
    svc = _svc()
    boards = await svc.list_boards()
    return BoardListResponse(
        items=[_board_to_response(b) for b in boards],
        total=len(boards),
    )


@router.post("/boards", response_model=BoardResponse, status_code=201)
async def create_board(body: BoardCreate) -> BoardResponse:
    from myrm_agent_harness.toolkits.kanban.types import BoardSettings

    svc = _svc()
    board = await svc.create_board(
        name=body.name,
        description=body.description,
        settings=BoardSettings(
            max_concurrent_tasks=body.max_concurrent_tasks,
            heartbeat_interval_seconds=body.heartbeat_interval_seconds,
            zombie_timeout_seconds=body.zombie_timeout_seconds,
            max_retries_per_task=body.max_retries_per_task,
            auto_block_after_consecutive_failures=body.auto_block_after_consecutive_failures,
            specify_max_tokens=body.specify_max_tokens,
            auto_specify_on_create=body.auto_specify_on_create,
            default_workdir=body.default_workdir,
        ),
    )
    return _board_to_response(board)


@router.get("/boards/{board_id}", response_model=BoardResponse)
async def get_board(board_id: str) -> BoardResponse:
    svc = _svc()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")
    return _board_to_response(board)


@router.patch("/boards/{board_id}", response_model=BoardResponse)
async def update_board(board_id: str, body: BoardUpdate) -> BoardResponse:
    from myrm_agent_harness.toolkits.kanban.types import BoardSettings

    svc = _svc()
    settings: BoardSettings | None = None
    needs_settings = any(
        v is not None
        for v in (
            body.max_concurrent_tasks,
            body.specify_max_tokens,
            body.auto_specify_on_create,
            body.default_workdir,
        )
    )
    if needs_settings:
        board = await svc.get_board(board_id)
        if board is None:
            raise HTTPException(404, f"Board {board_id} not found")
        settings = BoardSettings(
            max_concurrent_tasks=(
                body.max_concurrent_tasks
                if body.max_concurrent_tasks is not None
                else board.settings.max_concurrent_tasks
            ),
            heartbeat_interval_seconds=board.settings.heartbeat_interval_seconds,
            zombie_timeout_seconds=board.settings.zombie_timeout_seconds,
            max_retries_per_task=board.settings.max_retries_per_task,
            auto_block_after_consecutive_failures=board.settings.auto_block_after_consecutive_failures,
            specify_max_tokens=(
                body.specify_max_tokens
                if body.specify_max_tokens is not None
                else board.settings.specify_max_tokens
            ),
            auto_specify_on_create=(
                body.auto_specify_on_create
                if body.auto_specify_on_create is not None
                else board.settings.auto_specify_on_create
            ),
            default_workdir=(
                body.default_workdir
                if body.default_workdir is not None
                else board.settings.default_workdir
            ),
        )

    updated = await svc.update_board(
        board_id,
        name=body.name,
        description=body.description,
        settings=settings,
    )
    if updated is None:
        raise HTTPException(404, f"Board {board_id} not found")
    return _board_to_response(updated)


@router.delete("/boards/{board_id}", status_code=204)
async def delete_board(board_id: str) -> None:
    svc = _svc()
    deleted = await svc.delete_board(board_id)
    if not deleted:
        raise HTTPException(404, f"Board {board_id} not found")


@router.get("/boards/{board_id}/summary", response_model=BoardSummaryResponse)
async def board_summary(board_id: str) -> BoardSummaryResponse:
    svc = _svc()
    data = await svc.board_summary(board_id)
    if data is None:
        raise HTTPException(404, f"Board {board_id} not found")

    by_agent = [
        AgentTaskCounts(
            agent_id=agent_id,
            counts=counts,
            total=sum(counts.values()),
        )
        for agent_id, counts in data.by_agent.items()
    ]

    return BoardSummaryResponse(
        board=_board_to_response(data.board),
        task_counts=data.task_counts,
        total_tasks=data.total_tasks,
        dispatcher_active=data.dispatcher_active,
        by_agent=by_agent,
        oldest_ready_age_seconds=data.oldest_ready_age_seconds,
    )


# ---------------------------------------------------------------------------
# Board events
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}/events", response_model=BoardEventListResponse)
async def list_board_events(
    board_id: str,
    kinds: str | None = Query(None, description="Comma-separated event kinds to filter"),
    assignee: str | None = Query(None, description="Filter by task assignee agent_id"),
    since_id: int | None = Query(None, ge=0),
    since_time: str | None = Query(None, description="ISO datetime; only events after this time"),
    limit: int = Query(50, ge=1, le=200),
) -> BoardEventListResponse:
    """Board-level aggregated event timeline with task metadata."""
    from datetime import datetime as dt

    svc = _svc()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")

    parsed_kinds = (
        [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    )
    parsed_since_time: dt | None = None
    if since_time:
        try:
            parsed_since_time = dt.fromisoformat(since_time)
        except ValueError as exc:
            raise HTTPException(400, "Invalid since_time format; use ISO 8601") from exc

    events = await svc.list_board_events(
        board_id,
        kinds=parsed_kinds,
        assignee=assignee,
        since_id=since_id,
        since_time=parsed_since_time,
        limit=limit,
    )
    return BoardEventListResponse(
        items=[BoardEventResponse(**e) for e in events],
        total=len(events),
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
    svc = _svc()
    status: TaskStatus | None = None
    if status_filter:
        try:
            status = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status_filter}") from None

    tasks = await svc.list_tasks(
        board_id, status=status, agent_id=agent_id, limit=limit, offset=offset
    )
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
            completion_criteria=criteria if isinstance(criteria, str) else None,
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
        diags = _diag_engine.evaluate(t, rule_ids=CARD_FAST_RULES)
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
    svc = _svc()
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
                400, f"Invalid initial_status: {body.initial_status}",
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
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return await _task_response_with_attachments(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: str, body: TaskUpdate) -> TaskResponse:
    svc = _svc()
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

    svc = _svc()
    try:
        block_kind: BlockKind | None = None
        if body.block_kind:
            try:
                block_kind = BlockKind(body.block_kind)
            except ValueError:
                raise HTTPException(400, f"Invalid block_kind: {body.block_kind}") from None
        task = await svc.move_task(
            task_id, target_status,
            force=body.force,
            block_kind=block_kind,
            blocked_reason=body.blocked_reason,
            scheduled_until=body.scheduled_until,
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
    svc = _svc()
    try:
        result = await svc.promote_task(task_id, force=body.force, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return PromoteResponse(
        promoted=result.promoted,
        forced=result.forced,
        reason=result.reason,
        unmet_parents=[
            {"task_id": p["task_id"], "title": p["title"], "status": p["status"]}
            for p in result.unmet_parents
        ],
    )


@router.post("/tasks/{task_id}/reclaim", response_model=ReclaimResponse)
async def reclaim_task(task_id: str, body: ReclaimRequest) -> ReclaimResponse:
    svc = _svc()
    try:
        task = await svc.reclaim_task(
            task_id, reason=body.reason, new_agent_id=body.new_agent_id,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    return ReclaimResponse(reclaimed=True, task=await _task_response_with_attachments(task))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str) -> None:
    svc = _svc()
    deleted = await svc.delete_task(task_id)
    if not deleted:
        raise HTTPException(404, f"Task {task_id} not found")


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

_BULK_VALID_ACTIONS = {"move", "archive", "reassign", "reclaim", "delete"}


@router.post(
    "/boards/{board_id}/tasks/bulk-action",
    response_model=BulkActionResponse,
)
async def bulk_action(board_id: str, body: BulkActionRequest) -> BulkActionResponse:
    if body.action not in _BULK_VALID_ACTIONS:
        raise HTTPException(
            400,
            f"Invalid action: {body.action}. Must be one of: {', '.join(sorted(_BULK_VALID_ACTIONS))}",
        )
    if body.action == "delete" and not body.confirm:
        raise HTTPException(
            400, "Bulk delete requires confirm=true"
        )

    svc = _svc()
    results: list[BulkActionItemResult] = []

    for task_id in body.task_ids:
        try:
            if body.action == "archive":
                task = await svc.move_task(task_id, TaskStatus.ARCHIVED)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "move":
                status_str = body.params.get("status")
                if not status_str:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Missing params.status"))
                    continue
                try:
                    target = TaskStatus(status_str)
                except ValueError:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error=f"Invalid status: {status_str}"))
                    continue
                force = body.params.get("force", "").lower() in ("true", "1")
                task = await svc.move_task(task_id, target, force=force)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "reassign":
                agent_id = body.params.get("agent_id")
                task = await svc.update_task(task_id, agent_id=agent_id)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "reclaim":
                reason = body.params.get("reason")
                new_agent_id = body.params.get("new_agent_id")
                task = await svc.reclaim_task(
                    task_id, reason=reason, new_agent_id=new_agent_id,
                )
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "delete":
                deleted = await svc.delete_task(task_id)
                if not deleted:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

        except (ValueError, Exception) as exc:
            results.append(BulkActionItemResult(task_id=task_id, success=False, error=str(exc)))

    succeeded = sum(1 for r in results if r.success)
    return BulkActionResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )


# ---------------------------------------------------------------------------
# Run & Event endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/runs", response_model=RunListResponse)
async def list_task_runs(task_id: str) -> RunListResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    runs = await svc.list_runs(task_id)
    return RunListResponse(
        items=[
            RunResponse(
                run_id=r.run_id,
                task_id=r.task_id,
                worker_id=r.worker_id,
                started_at=r.started_at,
                ended_at=r.ended_at,
                outcome=r.outcome.value if r.outcome else None,
                summary=r.summary,
                error=r.error,
                duration_seconds=r.duration_seconds,
            )
            for r in runs
        ],
        total=len(runs),
    )


@router.get("/tasks/{task_id}/events", response_model=EventListResponse)
async def list_task_events(
    task_id: str,
    since_id: int | None = Query(None, ge=0),
) -> EventListResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    events = await svc.list_events(task_id, since_id=since_id)
    return EventListResponse(
        items=[
            EventResponse(
                event_id=e.event_id,
                task_id=e.task_id,
                kind=e.kind.value,
                payload=e.payload,
                run_id=e.run_id,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=len(events),
    )


@router.post("/tasks/{task_id}/comments", response_model=EventResponse, status_code=201)
async def add_comment(task_id: str, body: CommentCreate) -> EventResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    event = await svc.add_comment(task_id, body.body, author=body.author)
    return EventResponse(
        event_id=event.event_id,
        task_id=event.task_id,
        kind=event.kind.value,
        payload=event.payload,
        run_id=event.run_id,
        created_at=event.created_at,
    )


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/diagnostics", response_model=TaskDiagnosticsResponse)
async def get_task_diagnostics(task_id: str) -> TaskDiagnosticsResponse:
    """Full diagnostics for a single task (drawer-level).

    Runs all rules including dead_dependency (requires context).
    """
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")

    from myrm_agent_harness.toolkits.kanban.diagnostics import DiagnosticContext

    context: DiagnosticContext | None = None
    if task.status == TaskStatus.BACKLOG:
        parent_ids = await svc.store.list_parents(task_id)
        if parent_ids:
            parent_statuses: dict[str, str] = {}
            for pid in parent_ids:
                parent = await svc.get_task(pid)
                if parent:
                    parent_statuses[pid] = parent.status.value
            context = DiagnosticContext(
                parent_task_ids=tuple(parent_ids),
                parent_statuses=parent_statuses,
            )

    diags = _diag_engine.evaluate(task, context=context)
    return TaskDiagnosticsResponse(
        task_id=task_id,
        diagnostics=[
            TaskDiagnosticResponse(
                rule_id=d.rule_id,
                severity=d.severity.value,
                title=d.title,
                detail=d.detail,
                actions=[
                    DiagnosticActionResponse(
                        kind=a.kind,
                        label=a.label,
                        payload=dict(a.payload),
                        suggested=a.suggested,
                    )
                    for a in d.actions
                ],
            )
            for d in diags
        ],
    )


# ---------------------------------------------------------------------------
# Board edges (batch)
# ---------------------------------------------------------------------------


@router.get("/boards/{board_id}/edges", response_model=EdgeListResponse)
async def list_board_edges(board_id: str) -> EdgeListResponse:
    svc = _svc()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")
    edges = await svc.list_board_edges(board_id)
    return EdgeListResponse(
        items=[
            DependencyResponse(
                parent_task_id=e.parent_task_id,
                child_task_id=e.child_task_id,
            )
            for e in edges
        ],
        total=len(edges),
    )


# ---------------------------------------------------------------------------
# Dependency endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/dependencies", response_model=DependencyListResponse)
async def list_dependencies(task_id: str) -> DependencyListResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    parents = await svc.list_task_dependencies(task_id)
    return DependencyListResponse(items=parents, total=len(parents))


@router.get("/tasks/{task_id}/dependents", response_model=DependencyListResponse)
async def list_dependents(task_id: str) -> DependencyListResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    children = await svc.list_task_dependents(task_id)
    return DependencyListResponse(items=children, total=len(children))


@router.post(
    "/tasks/{task_id}/dependencies",
    response_model=DependencyResponse,
    status_code=201,
)
async def add_dependency(task_id: str, body: DependencyRequest) -> DependencyResponse:
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    parent = await svc.get_task(body.parent_task_id)
    if parent is None:
        raise HTTPException(404, f"Parent task {body.parent_task_id} not found")

    try:
        edge = await svc.add_dependency(task_id, body.parent_task_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return DependencyResponse(
        parent_task_id=edge.parent_task_id,
        child_task_id=edge.child_task_id,
    )


@router.delete("/tasks/{task_id}/dependencies/{parent_task_id}", status_code=204)
async def remove_dependency(task_id: str, parent_task_id: str) -> None:
    svc = _svc()
    removed = await svc.remove_dependency(task_id, parent_task_id)
    if not removed:
        raise HTTPException(404, "Dependency not found")


# ---------------------------------------------------------------------------
# Specify (TRIAGE → spec rewrite) endpoints
# ---------------------------------------------------------------------------


def _outcome_to_response(outcome: object) -> SpecifyOutcomeResponse:
    """Map a harness SpecifyOutcome dataclass to the API DTO."""
    return SpecifyOutcomeResponse(
        task_id=getattr(outcome, "task_id", ""),
        ok=bool(getattr(outcome, "ok", False)),
        reason=str(getattr(outcome, "reason", "")),
        new_title=getattr(outcome, "new_title", None),
        new_body=getattr(outcome, "new_body", None),
        prompt_tokens=getattr(outcome, "prompt_tokens", None),
        completion_tokens=getattr(outcome, "completion_tokens", None),
        persisted=bool(getattr(outcome, "persisted", False)),
    )


@router.post(
    "/tasks/{task_id}/specify",
    response_model=SpecifyOutcomeResponse,
)
async def specify_task(
    task_id: str,
    dry_run: bool = Query(True, description="True returns a preview without persisting."),
) -> SpecifyOutcomeResponse:
    """Run the TaskSpecifier on a single TRIAGE task.

    dry_run=True returns a preview SpecifyOutcome (UI Apply/Reject loop).
    dry_run=False persists the spec, emits SPECIFIED event, and promotes
    TRIAGE → READY (or BACKLOG when dependencies are unmet).
    """
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.specify_task(task_id, persist=not dry_run)
    return _outcome_to_response(outcome)


@router.post(
    "/tasks/{task_id}/apply-spec",
    response_model=SpecifyOutcomeResponse,
)
async def apply_spec(
    task_id: str,
    body: ApplySpecRequest,
) -> SpecifyOutcomeResponse:
    """Persist a previously-previewed spec without re-invoking the LLM.

    The frontend calls this after the user reviews a dry-run preview and
    clicks "Apply & Promote". The cached new_title / new_body from the
    preview are sent in the request body so the LLM is never called twice.
    """
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.apply_spec(
        task_id,
        new_title=body.new_title,
        new_body=body.new_body,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
    )
    return _outcome_to_response(outcome)


@router.post(
    "/boards/{board_id}/specify-all",
    response_model=SpecifyAllResponse,
)
async def specify_all_triage(
    board_id: str,
    dry_run: bool = Query(True, description="True returns previews without persisting."),
) -> SpecifyAllResponse:
    """Run the TaskSpecifier on every TRIAGE task of a board concurrently.

    Bounded concurrency (3 in-flight LLM calls) prevents stampedes.
    Failures are reported per-task; the sweep never aborts on a single
    failure.
    """
    svc = _svc()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")

    outcomes = await svc.specify_all_triage(board_id, persist=not dry_run)
    return SpecifyAllResponse(
        items=[_outcome_to_response(o) for o in outcomes],
        total=len(outcomes),
        persisted=not dry_run,
    )


# ---------------------------------------------------------------------------
# Decompose (TRIAGE → child task graph) endpoints
# ---------------------------------------------------------------------------


def _decompose_to_response(outcome: object) -> DecomposeOutcomeResponse:
    """Map a harness DecomposeOutcome dataclass to the API DTO."""
    children_raw = getattr(outcome, "children", ()) or ()
    return DecomposeOutcomeResponse(
        task_id=getattr(outcome, "task_id", ""),
        ok=bool(getattr(outcome, "ok", False)),
        fanout=bool(getattr(outcome, "fanout", False)),
        children=[
            DecomposeChildResponse(
                title=c.title,
                body=c.body,
                assignee=c.assignee,
                parent_indices=list(c.parent_indices),
                extra_skill_ids=list(getattr(c, "extra_skill_ids", ())),
            )
            for c in children_raw
        ],
        rationale=str(getattr(outcome, "rationale", "")),
        reason=str(getattr(outcome, "reason", "")),
        new_title=getattr(outcome, "new_title", None),
        new_body=getattr(outcome, "new_body", None),
        new_assignee=getattr(outcome, "new_assignee", None),
        child_ids=list(getattr(outcome, "child_ids", ()) or ()),
        prompt_tokens=getattr(outcome, "prompt_tokens", None),
        completion_tokens=getattr(outcome, "completion_tokens", None),
        persisted=bool(getattr(outcome, "persisted", False)),
    )


@router.post(
    "/tasks/{task_id}/decompose",
    response_model=DecomposeOutcomeResponse,
)
async def decompose_task(task_id: str) -> DecomposeOutcomeResponse:
    """Preview a decomposition for a TRIAGE task (always dry-run).

    Returns the LLM-proposed child task graph for the user to review
    in the DecomposeDialog. The user then calls apply-decompose to persist.
    """
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    outcome = await svc.decompose_task(task_id)
    return _decompose_to_response(outcome)


@router.post(
    "/tasks/{task_id}/apply-decompose",
    response_model=DecomposeOutcomeResponse,
)
async def apply_decompose(
    task_id: str,
    body: ApplyDecomposeRequest,
) -> DecomposeOutcomeResponse:
    """Persist a previously-previewed decomposition.

    When ``fanout=true``, creates child tasks atomically and promotes
    root TRIAGE → BACKLOG.
    When ``fanout=false``, applies the tightened title/body/assignee
    to the task and promotes TRIAGE → READY (Specify fallback).
    """
    svc = _svc()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")

    if not body.fanout:
        outcome = await svc.apply_no_fanout(
            task_id,
            new_title=body.new_title,
            new_body=body.new_body,
            new_assignee=body.new_assignee,
            rationale=body.rationale,
            prompt_tokens=body.prompt_tokens,
            completion_tokens=body.completion_tokens,
        )
        return _decompose_to_response(outcome)

    from myrm_agent_harness.toolkits.kanban.protocols import DecomposeChildSpec

    children = [
        DecomposeChildSpec(
            title=c.title,
            body=c.body,
            assignee=c.assignee,
            parent_indices=tuple(c.parent_indices),
            extra_skill_ids=tuple(c.extra_skill_ids),
        )
        for c in body.children
    ]

    outcome = await svc.apply_decompose(
        task_id,
        children=children,
        rationale=body.rationale,
        prompt_tokens=body.prompt_tokens,
        completion_tokens=body.completion_tokens,
    )
    return _decompose_to_response(outcome)
