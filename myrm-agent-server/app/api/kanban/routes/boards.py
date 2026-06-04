"""Kanban API routes — boards."""

from __future__ import annotations

from fastapi import HTTPException, Query

from app.api.kanban.http_common import (
    _board_to_response,
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    AgentTaskCounts,
    BoardCreate,
    BoardEventListResponse,
    BoardEventResponse,
    BoardListResponse,
    BoardResponse,
    BoardSummaryResponse,
    BoardUpdate,
)

# ---------------------------------------------------------------------------
# Board endpoints
# ---------------------------------------------------------------------------


@router.get("/boards", response_model=BoardListResponse)
async def list_boards() -> BoardListResponse:
    svc = get_kanban_service()
    boards = await svc.list_boards()
    return BoardListResponse(
        items=[_board_to_response(b) for b in boards],
        total=len(boards),
    )


@router.post("/boards", response_model=BoardResponse, status_code=201)
async def create_board(body: BoardCreate) -> BoardResponse:
    from myrm_agent_harness.toolkits.kanban.types import BoardSettings

    svc = get_kanban_service()
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
    svc = get_kanban_service()
    board = await svc.get_board(board_id)
    if board is None:
        raise HTTPException(404, f"Board {board_id} not found")
    return _board_to_response(board)


@router.patch("/boards/{board_id}", response_model=BoardResponse)
async def update_board(board_id: str, body: BoardUpdate) -> BoardResponse:
    from myrm_agent_harness.toolkits.kanban.types import BoardSettings

    svc = get_kanban_service()
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
    svc = get_kanban_service()
    deleted = await svc.delete_board(board_id)
    if not deleted:
        raise HTTPException(404, f"Board {board_id} not found")


@router.get("/boards/{board_id}/summary", response_model=BoardSummaryResponse)
async def board_summary(board_id: str) -> BoardSummaryResponse:
    svc = get_kanban_service()
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

    svc = get_kanban_service()
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


