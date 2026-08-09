"""Matrix Eval API Router — cross-profile comparison endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks, HTTPException
- app.core.eval.matrix::run_matrix_eval_background, get_matrix_eval_status, ...

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).

[POS]
HTTP layer for cross-profile matrix evaluation (multi-profile comparison on
the same dataset). Kept in its own module so app.api.eval.router stays a
thin aggregator within the eval module's line budget.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

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


async def _matrix_status_generator() -> AsyncGenerator[str, None]:
    last_state_str = ""
    while True:
        status_info = get_matrix_eval_status()
        current_state_str = json.dumps(status_info)
        if current_state_str != last_state_str:
            yield f"data: {current_state_str}\n\n"
            last_state_str = current_state_str

        if not status_info.get("is_running"):
            yield "event: close\ndata: {}\n\n"
            break

        await asyncio.sleep(0.5)


@router.get("/matrix/stream")
async def stream_matrix_evaluation_status() -> StreamingResponse:
    """Stream the current status of the matrix evaluation via SSE."""
    return StreamingResponse(
        _matrix_status_generator(),
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
