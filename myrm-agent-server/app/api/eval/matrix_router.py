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
from pydantic import BaseModel, Field

from app.api.eval.streaming import stream_status_events
from app.core.eval.matrix import (
    abort_matrix_eval,
    get_latest_matrix_report,
    get_matrix_eval_status,
    run_layer_eval_background,
    run_matrix_eval_background,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["eval"])


class RunMatrixEvalRequest(BaseModel):
    profile_ids: list[str]
    dataset_id: str | None = None
    benchmark_mode: bool = False


class RunLayerEvalRequest(BaseModel):
    benchmark_id: str
    profile_id: str | None = None
    limit: int | None = Field(default=None, ge=1)


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
    """Abort the currently running matrix or layered evaluation."""
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
    """Get the latest matrix or layered evaluation report."""
    report = get_latest_matrix_report()
    if not report:
        return {"status": "not_found", "report": None}
    return {"status": "success", "report": report}


@router.post("/matrix/layers-run")
async def run_layered_evaluation(
    background_tasks: BackgroundTasks,
    request: RunLayerEvalRequest,
) -> dict[str, object]:
    """Start a layered (config-increment) evaluation on an external benchmark.

    The same dataset runs across the ascending layer chain (bare -> core ->
    skills -> memory), reusing the matrix state machine and report directory.
    Pre-flights mirror the memory A/B flow: the memory layer requires a
    reachable embedding model, LLM-judge benchmarks require a resolvable judge
    model, and web-search benchmarks require a configured search provider —
    each fails fast with explicit guidance instead of a misleading run.
    """
    status_info = get_matrix_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    from myrm_agent_harness.api.config import ConfigIncompleteError

    from app.core.eval.benchmarks import (
        benchmark_needs_judge,
        benchmark_required_tools,
        is_known_benchmark,
    )

    if not is_known_benchmark(request.benchmark_id):
        return {
            "status": "error",
            "error": f"Unknown benchmark: {request.benchmark_id}",
        }

    # The memory layer is a core part of the chain, so a missing or
    # unreachable embedding model would silently degrade it to a memory-free
    # arm and produce a misleading "memory has no effect" result.
    from app.services.agent.platform_config import verify_platform_embedding_ready

    try:
        await verify_platform_embedding_ready()
    except ConfigIncompleteError as exc:
        return {
            "status": "error",
            "error": exc.user_friendly_message.get("en", str(exc)),
        }

    if "web_search" in benchmark_required_tools(request.benchmark_id):
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            verify_search_service_available,
        )

        try:
            configs = await load_user_configs()
        except ConfigIncompleteError as exc:
            return {
                "status": "error",
                "error": exc.user_friendly_message.get("en", str(exc)),
            }
        if not configs.search_is_user_configured:
            return {
                "status": "error",
                "error": (
                    f"{request.benchmark_id} requires web search, but no search "
                    "provider is configured. Enable a search provider in settings "
                    "before running this benchmark."
                ),
            }
        if not await verify_search_service_available(configs.search_cfg):
            return {
                "status": "error",
                "error": (
                    f"{request.benchmark_id} requires web search, but the "
                    "configured search provider is unreachable. Fix the search "
                    "service before running this benchmark."
                ),
            }

    if benchmark_needs_judge(request.benchmark_id):
        from app.core.eval.model_config import _resolve_judge_config

        judge, _judge_label = await _resolve_judge_config()
        if judge is None:
            return {
                "status": "error",
                "error": (
                    f"{request.benchmark_id} is graded by an LLM judge, but no "
                    "model provider is configured. Configure a model in settings "
                    "before running this benchmark."
                ),
            }

    post_probe_status = get_matrix_eval_status()
    if post_probe_status.get("is_running"):
        return {"status": "already_running", "info": post_probe_status}

    background_tasks.add_task(
        run_layer_eval_background,
        benchmark_id=request.benchmark_id,
        profile_id=request.profile_id,
        limit=request.limit,
    )
    return {"status": "started"}
