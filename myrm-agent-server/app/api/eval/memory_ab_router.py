"""Memory A/B Eval API Router — memory-on vs memory-off comparison endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks
- app.core.eval.memory_ab::run_memory_ab_background, get_memory_ab_status, ...
- app.services.agent.platform_config::verify_platform_embedding_ready

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).

[POS]
HTTP layer for the Memory A/B evaluation. The /memory-ab/run endpoint
validates that an embedding model is both configured and reachable before
starting the run — a missing or unusable embedding backend makes the
memory-on arm silently degrade to a memory-free agent and produce a
misleading "memory has no effect" result.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.eval.memory_ab import (
    _init_memory_ab_state,
    abort_memory_ab,
    get_latest_memory_ab_report,
    get_memory_ab_report,
    get_memory_ab_report_history,
    get_memory_ab_status,
    run_memory_ab_background,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["eval"])


class RunMemoryAbRequest(BaseModel):
    subset_id: str
    profile_id: str | None = None


@router.post("/memory-ab/run")
async def run_memory_ab_evaluation(
    background_tasks: BackgroundTasks,
    request: RunMemoryAbRequest,
) -> dict[str, object]:
    """Start a memory-on vs memory-off A/B comparison on a WBBench subset."""
    status_info = get_memory_ab_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    from app.core.eval.wb_bench import WB_BENCH_SUBSETS

    if request.subset_id not in WB_BENCH_SUBSETS:
        return {
            "status": "error",
            "error": f"Unknown WBBench subset: {request.subset_id}",
        }

    # A memory A/B test is only meaningful when an embedding model is both
    # configured and reachable: without one the memory-on arm silently
    # degrades to a memory-free agent (tool_setup._create_memory_tools) and
    # the run yields a misleading "memory has no effect" result. Fail fast
    # before the WBBench download so the user gets explicit guidance instead.
    from myrm_agent_harness.api.config import ConfigIncompleteError

    from app.services.agent.platform_config import (
        verify_platform_embedding_ready,
    )

    try:
        await verify_platform_embedding_ready()
    except ConfigIncompleteError as exc:
        return {
            "status": "error",
            "error": exc.user_friendly_message.get("en", str(exc)),
        }

    # Re-check after the (potentially slow) embedding probe: two concurrent
    # requests can both pass the pre-probe guard, and only the probe keeps
    # the window open long enough to matter. The re-check is synchronous, so
    # the following _init_memory_ab_state cannot be interleaved.
    post_probe_status = get_memory_ab_status()
    if post_probe_status.get("is_running"):
        return {"status": "already_running", "info": post_probe_status}

    # Mark state as running synchronously before the response is sent (same
    # race guard as the WBBench run flow: BackgroundTasks start after the
    # response, so the SSE stream would otherwise read a stale idle frame).
    _init_memory_ab_state(request.subset_id)
    background_tasks.add_task(
        run_memory_ab_background,
        subset_id=request.subset_id,
        profile_id=request.profile_id,
    )
    return {"status": "started"}


@router.post("/memory-ab/abort")
async def abort_memory_ab_evaluation() -> dict[str, object]:
    """Abort the currently running memory A/B evaluation."""
    success = abort_memory_ab()
    if not success:
        return {"status": "not_running"}
    return {"status": "aborted"}


@router.get("/memory-ab/status")
async def get_memory_ab_evaluation_status() -> dict[str, object]:
    """Get the current status of the memory A/B evaluation."""
    return get_memory_ab_status()


async def _memory_ab_status_generator() -> AsyncGenerator[str, None]:
    last_state_str = ""
    while True:
        status_info = get_memory_ab_status()
        current_state_str = json.dumps(status_info)
        if current_state_str != last_state_str:
            yield f"data: {current_state_str}\n\n"
            last_state_str = current_state_str

        if not status_info.get("is_running"):
            yield "event: close\ndata: {}\n\n"
            break

        await asyncio.sleep(0.5)


@router.get("/memory-ab/stream")
async def stream_memory_ab_evaluation_status() -> StreamingResponse:
    """Stream the current status of the memory A/B evaluation via SSE."""
    return StreamingResponse(
        _memory_ab_status_generator(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.get("/memory-ab/reports/latest")
async def get_latest_memory_ab_evaluation_report() -> dict[str, object]:
    """Get the latest memory A/B evaluation report."""
    report = get_latest_memory_ab_report()
    if not report:
        return {"status": "not_found", "report": None}
    return {"status": "success", "report": report}


@router.get("/memory-ab/reports/history")
async def get_memory_ab_report_history_endpoint() -> dict[str, object]:
    """Get the history of memory A/B evaluation reports, newest first."""
    history = get_memory_ab_report_history()
    return {"status": "success", "reports": history}


@router.get("/memory-ab/reports/{timestamp}")
async def get_memory_ab_report_by_timestamp(timestamp: int) -> dict[str, object]:
    """Get a specific memory A/B report by its run timestamp."""
    report = get_memory_ab_report(timestamp)
    if not report:
        return {"status": "not_found", "report": None}
    return {"status": "success", "report": report}
