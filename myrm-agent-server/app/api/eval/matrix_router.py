"""Matrix Eval API Router — cross-profile comparison endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks, HTTPException
- app.api.eval.streaming::stream_status_events (POS: eval SSE 状态流公共 helper)
- app.core.eval.matrix::run_matrix_eval_background, get_matrix_eval_status, ...

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).

[POS]
HTTP layer for cross-profile matrix evaluation (multi-profile comparison on
the same dataset). Provides its own endpoints so the matrix feature stays a
self-contained sub-router under the /eval prefix.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.eval.streaming import stream_status_events
from app.core.eval.matrix import (
    abort_matrix_eval,
    get_latest_matrix_report,
    get_matrix_eval_status,
    run_matrix_eval_background,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["eval"])


class RunMatrixEvalRequest(BaseModel):
    profile_ids: list[str]
    dataset_id: str | None = None
    benchmark_mode: bool = False


@router.post("/matrix/run")
async def run_matrix_evaluation(
    background_tasks: BackgroundTasks,
    request: RunMatrixEvalRequest,
) -> dict[str, object]:
    """Start cross-profile matrix evaluation in the background."""
    if len(request.profile_ids) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Matrix eval requires at least 2 profiles",
        )

    matrix_status = get_matrix_eval_status()
    if matrix_status.get("is_running"):
        return {"status": "already_running", "info": matrix_status}

    background_tasks.add_task(
        run_matrix_eval_background,
        dataset_id=request.dataset_id,
        profile_ids=request.profile_ids,
        benchmark_mode=request.benchmark_mode,
    )
    return {"status": "started"}


@router.post("/matrix/abort")
async def abort_matrix_evaluation() -> dict[str, object]:
    """Abort the currently running matrix evaluation."""
    success = abort_matrix_eval()
    if not success:
        return {"status": "not_running"}
    return {"status": "aborted"}


@router.get("/matrix/status")
async def get_matrix_evaluation_status() -> dict[str, object]:
    """Get the current status of the matrix evaluation."""
    return get_matrix_eval_status()


@router.get("/matrix/stream")
async def stream_matrix_evaluation_status() -> StreamingResponse:
    """Stream the current status of the matrix evaluation via SSE."""
    return StreamingResponse(
        stream_status_events(get_matrix_eval_status),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.get("/matrix/reports/latest")
async def get_latest_matrix_evaluation_report() -> dict[str, object]:
    """Get the latest matrix evaluation report."""
    report = get_latest_matrix_report()
    if not report:
        return {"status": "not_found", "report": None}
    return {"status": "success", "report": report}
