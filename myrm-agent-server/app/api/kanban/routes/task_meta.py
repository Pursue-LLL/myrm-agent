"""Kanban API routes — task_meta."""

from __future__ import annotations

from fastapi import HTTPException, Query
from myrm_agent_harness.toolkits.kanban.types import (
    TaskStatus,
)

from app.api.kanban.http_common import (
    diag_engine,
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    CommentCreate,
    DependencyListResponse,
    DependencyRequest,
    DependencyResponse,
    DiagnosticActionResponse,
    EdgeListResponse,
    EventListResponse,
    EventResponse,
    RunListResponse,
    RunResponse,
    TaskDiagnosticResponse,
    TaskDiagnosticsResponse,
)

# ---------------------------------------------------------------------------
# Run & Event endpoints
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/runs", response_model=RunListResponse)
async def list_task_runs(task_id: str) -> RunListResponse:
    svc = get_kanban_service()
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
    svc = get_kanban_service()
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
    svc = get_kanban_service()
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
    svc = get_kanban_service()
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

    diags = diag_engine.evaluate(task, context=context)
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
    svc = get_kanban_service()
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
    svc = get_kanban_service()
    task = await svc.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"Task {task_id} not found")
    parents = await svc.list_task_dependencies(task_id)
    return DependencyListResponse(items=parents, total=len(parents))


@router.get("/tasks/{task_id}/dependents", response_model=DependencyListResponse)
async def list_dependents(task_id: str) -> DependencyListResponse:
    svc = get_kanban_service()
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
    svc = get_kanban_service()
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
    svc = get_kanban_service()
    removed = await svc.remove_dependency(task_id, parent_task_id)
    if not removed:
        raise HTTPException(404, "Dependency not found")


