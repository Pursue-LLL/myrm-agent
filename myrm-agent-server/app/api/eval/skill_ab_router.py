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
from app.core.eval.benchmarks import (
    benchmark_needs_judge,
    benchmark_required_tools,
    is_known_benchmark,
)
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
        raise HTTPException(status_code=409, detail="A Skill A/B evaluation is already in progress.")

    if not is_known_benchmark(request.benchmark_id):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown benchmark '{request.benchmark_id}'.",
        )

    if "web_search" in benchmark_required_tools(request.benchmark_id):
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import verify_search_service_available
        from myrm_agent_harness.api.config import ConfigIncompleteError

        try:
            configs = await load_user_configs()
        except ConfigIncompleteError as exc:
            raise HTTPException(
                status_code=400,
                detail=exc.user_friendly_message.get("en", str(exc)),
            ) from exc
        if not configs.search_is_user_configured:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{request.benchmark_id} requires web search, but no search "
                    "provider is configured. Enable a search provider in settings first."
                ),
            )
        if not await verify_search_service_available(configs.search_cfg):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{request.benchmark_id} requires web search, but the configured "
                    "search provider is unreachable. Fix the search service first."
                ),
            )

    if benchmark_needs_judge(request.benchmark_id):
        from app.core.eval.model_config import _resolve_judge_config

        judge, _judge_label = await _resolve_judge_config()
        if judge is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{request.benchmark_id} is graded by an LLM judge, but no "
                    "model provider is configured. Configure a model in settings first."
                ),
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
