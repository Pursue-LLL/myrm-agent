"""Race endpoints: parallel lanes for one task, human picks the winner.

[INPUT]
- app.services.kanban.race_orchestrator (POS: Race fan-out / decide logic.)
- app.api.kanban.schemas (POS: Race request/response models.)

[OUTPUT]
- Estimate, start, lanes and decide endpoints on the shared kanban router.

[POS]
Thin HTTP layer over race_orchestrator. V1 is git-worktree tasks only.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.api.kanban.http_common import (
    _task_to_response,
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    RaceDecideRequest,
    RaceDecideResponse,
    RaceEstimateResponse,
    RaceLaneChangesResponse,
    RaceLaneFileResponse,
    RaceLaneResponse,
    RaceLanesResponse,
    RaceStartRequest,
    RaceStartResponse,
    TaskResponse,
)
from app.services.kanban.race_orchestrator import (
    LaneSpec,
    RaceError,
    estimate_race_cost,
    get_lane_changes,
    get_lane_file_contents,
    get_race_lanes,
    pick_race_winner,
    start_race,
)


def _race_error_to_http(exc: RaceError) -> HTTPException:
    status = 409
    if exc.code in ("unknown_task", "unknown_board", "not_a_lane"):
        status = 404
    if exc.code in ("bad_lane_count",):
        status = 400
    return HTTPException(status, detail={"code": exc.code, "message": str(exc)})


@router.get(
    "/boards/{board_id}/tasks/{task_id}/race/estimate",
    response_model=RaceEstimateResponse,
)
async def race_estimate(
    board_id: str, task_id: str, lanes: int = 3
) -> RaceEstimateResponse:
    _ = task_id
    svc = get_kanban_service()
    estimate = await estimate_race_cost(svc, board_id, min(max(lanes, 2), 5))
    return RaceEstimateResponse(**estimate.to_dict())


@router.post(
    "/boards/{board_id}/tasks/{task_id}/race",
    response_model=RaceStartResponse,
    status_code=201,
)
async def race_start(
    board_id: str, task_id: str, body: RaceStartRequest
) -> RaceStartResponse:
    svc = get_kanban_service()
    try:
        outcome = await start_race(
            svc,
            board_id,
            task_id,
            [
                LaneSpec(
                    agent_id=lane.agent_id,
                    model_override=lane.model_override,
                    instruction_variant=lane.instruction_variant,
                    title_suffix=lane.title_suffix,
                )
                for lane in body.lanes
            ],
            branch=body.branch,
            confirm_cost=body.confirm_cost,
        )
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    return RaceStartResponse(
        parent_task_id=outcome["parent_task_id"],
        lane_ids=outcome["lane_ids"],
        estimate=RaceEstimateResponse(**outcome["estimate"]),
    )


@router.get(
    "/boards/{board_id}/tasks/{task_id}/race",
    response_model=RaceLanesResponse,
)
async def race_lanes(board_id: str, task_id: str) -> RaceLanesResponse:
    svc = get_kanban_service()
    try:
        lanes = await get_race_lanes(svc, board_id, task_id)
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    responses: list[RaceLaneResponse] = []
    for lane in lanes:
        total_tokens = 0
        try:
            runs = await svc.list_runs(lane.task_id)
        except Exception:
            runs = []
        for run in runs:
            usage = run.token_usage or {}
            total_tokens += sum(
                value for value in usage.values() if isinstance(value, int)
            )
        responses.append(
            RaceLaneResponse(
                task_id=lane.task_id,
                title=lane.title,
                status=lane.status.value,
                agent_id=lane.agent_id,
                branch=lane.branch,
                result=lane.result,
                total_tokens=total_tokens,
            )
        )
    return RaceLanesResponse(parent_task_id=task_id, lanes=responses)


@router.post(
    "/boards/{board_id}/tasks/{task_id}/race/decide",
    response_model=RaceDecideResponse,
)
async def race_decide(
    board_id: str, task_id: str, body: RaceDecideRequest
) -> RaceDecideResponse:
    _ = board_id
    svc = get_kanban_service()
    try:
        outcome = await pick_race_winner(
            svc, task_id, body.winner_task_id, approver=body.approver
        )
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    return RaceDecideResponse(**outcome)


@router.get(
    "/boards/{board_id}/tasks/{task_id}/race/lanes/{lane_task_id}/changes",
    response_model=RaceLaneChangesResponse,
)
async def race_lane_changes(
    board_id: str, task_id: str, lane_task_id: str
) -> RaceLaneChangesResponse:
    """List files changed by a lane against the race target branch."""
    svc = get_kanban_service()
    try:
        outcome = await get_lane_changes(svc, board_id, task_id, lane_task_id)
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    return RaceLaneChangesResponse(**outcome)


@router.get(
    "/boards/{board_id}/tasks/{task_id}/race/lanes/{lane_task_id}/file",
    response_model=RaceLaneFileResponse,
)
async def race_lane_file(
    board_id: str, task_id: str, lane_task_id: str, path: str
) -> RaceLaneFileResponse:
    """Return target vs lane file contents for side-by-side review."""
    svc = get_kanban_service()
    try:
        outcome = await get_lane_file_contents(svc, board_id, task_id, lane_task_id, path)
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    return RaceLaneFileResponse(**outcome)


@router.get(
    "/boards/{board_id}/tasks/{task_id}/race/winner",
    response_model=TaskResponse,
)
async def race_winner(board_id: str, task_id: str) -> TaskResponse:
    """Return the decided winner task, if any."""
    from myrm_agent_harness.toolkits.kanban.types import TaskEventKind

    _ = board_id
    svc = get_kanban_service()
    try:
        await get_race_lanes(svc, board_id, task_id)
        events = await svc.list_events(task_id)
    except RaceError as exc:
        raise _race_error_to_http(exc) from None
    for event in reversed(events):
        if event.kind == TaskEventKind.RACE_DECIDED and event.payload:
            winner_id = event.payload.get("winner_task_id")
            if isinstance(winner_id, str):
                winner = await svc.get_task(winner_id)
                if winner is not None:
                    return await _task_to_response(winner)
    raise HTTPException(404, "No decided winner for this race yet")
