"""Skill A/B Eval API Router — Three-arm comparative evaluation endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks
- app.api.eval.streaming::stream_status_events
- app.core.eval.skill_ab::run_skill_ab_background, get_skill_ab_status, abort_skill_ab, ...
- app.core.eval.benchmarks::is_known_benchmark

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.eval.streaming import stream_status_events
from app.core.eval.benchmarks import is_known_benchmark
from app.core.eval.skill_ab import (
    abort_skill_ab,
    get_latest_skill_ab_report,
    get_skill_ab_report_history,
    get_skill_ab_status,
    run_skill_ab_background,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

router = APIRouter(tags=["eval"])


class RunSkillAbRequest(BaseModel):
    benchmark_id: str
    candidate_skill_id: str
    baseline_skill_id: str | None = None
    limit: int | None = Field(default=None, ge=1)


@router.post("/skill-ab/run")
async def run_skill_ab_evaluation(
    background_tasks: BackgroundTasks,
    request: RunSkillAbRequest,
) -> dict[str, object]:
    """Start a three-arm Skill A/B evaluation."""
    status = get_skill_ab_status()
    if status.get("is_running"):
        raise HTTPException(
            status_code=409, detail="A Skill A/B evaluation is already in progress."
        )

    if not is_known_benchmark(request.benchmark_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown benchmark '{request.benchmark_id}'.",
        )

    background_tasks.add_task(
        run_skill_ab_background,
        benchmark_id=request.benchmark_id,
        candidate_skill_id=request.candidate_skill_id,
        baseline_skill_id=request.baseline_skill_id,
        limit=request.limit,
    )

    return {
        "status": "started",
        "benchmark_id": request.benchmark_id,
        "candidate_skill_id": request.candidate_skill_id,
        "baseline_skill_id": request.baseline_skill_id,
    }


@router.get("/skill-ab/status")
async def get_skill_ab_run_status() -> dict[str, object]:
    """Get the current Skill A/B evaluation status."""
    return get_skill_ab_status()


@router.get("/skill-ab/status/stream")
async def stream_skill_ab_status() -> StreamingResponse:
    """SSE endpoint for streaming real-time Skill A/B run progress."""
    return StreamingResponse(
        stream_status_events(get_skill_ab_status),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.post("/skill-ab/abort")
async def abort_skill_ab_run() -> dict[str, object]:
    """Abort the running Skill A/B evaluation."""
    aborted = abort_skill_ab()
    return {"aborted": aborted}


@router.get("/skill-ab/report/latest")
async def get_latest_report() -> dict[str, object]:
    """Get the latest Skill A/B evaluation report."""
    report = get_latest_skill_ab_report()
    if not report:
        raise HTTPException(status_code=404, detail="No Skill A/B report found.")
    return report


@router.get("/skill-ab/reports")
async def list_reports() -> list[dict[str, object]]:
    """List historical Skill A/B reports."""
    return get_skill_ab_report_history()
