"""Memory A/B Eval API Router — memory-on vs memory-off comparison endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks
- app.api.eval.streaming::stream_status_events (POS: eval SSE 状态流公共 helper)
- app.core.eval.memory_ab::run_memory_ab_background, get_memory_ab_status, ...
- app.services.agent.platform_config::verify_platform_embedding_ready
- app.core.eval.benchmarks::is_known_benchmark, benchmark_required_tools
- app.core.channel_bridge.config_loader::load_user_configs,
  app.core.channel_bridge.config_parsers::verify_search_service_available
  (POS: memory A/B 在 benchmark_mode 下运行，web-search 基准需前置校验
  搜索配置/健康，避免两臂静默降级出误导性对比)

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).

[POS]
HTTP layer for the Memory A/B evaluation. The /memory-ab/run endpoint
validates, before starting the run, that the environment can actually
exercise both arms: an embedding model must be configured and reachable
(a missing embedding silently degrades the memory-on arm to a memory-free
agent), and — when the benchmark's tool whitelist requires web search —
a search provider must be configured and reachable (a missing search
backend silently produces a near-zero score on both arms). Both checks
fail fast with explicit guidance instead of a misleading comparison.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.eval.streaming import stream_status_events
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

router = APIRouter(tags=["eval"])


class RunMemoryAbRequest(BaseModel):
    benchmark_id: str
    profile_id: str | None = None
    limit: int | None = Field(default=None, ge=1)


@router.post("/memory-ab/run")
async def run_memory_ab_evaluation(
    background_tasks: BackgroundTasks,
    request: RunMemoryAbRequest,
) -> dict[str, object]:
    """Start a memory-on vs memory-off A/B comparison on an external benchmark."""
    status_info = get_memory_ab_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    from myrm_agent_harness.eval import get_benchmark

    from app.core.eval.benchmarks import is_known_benchmark

    spec = get_benchmark(request.benchmark_id)
    is_wb_bench = request.benchmark_id.startswith("wb-bench-")
    if not is_known_benchmark(request.benchmark_id) or not (is_wb_bench or (spec is not None and spec.supports_memory_ab)):
        return {
            "status": "error",
            "error": f"Benchmark does not support memory A/B: {request.benchmark_id}",
        }

    # A memory A/B test is only meaningful when an embedding model is both
    # configured and reachable: without one the memory-on arm silently
    # degrades to a memory-free agent (tool_setup._create_memory_tools) and
    # the run yields a misleading "memory has no effect" result. Fail fast
    # before the benchmark download so the user gets explicit guidance instead.
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

    # A memory A/B run executes both arms in benchmark_mode with the
    # benchmark's declared tool whitelist. When that whitelist requires web
    # search, a missing or unreachable search backend silently produces a
    # near-zero score on both arms — mirror the benchmark-run pre-flight so
    # the user gets explicit guidance instead of a misleading comparison.
    from app.core.eval.benchmarks import benchmark_needs_judge, benchmark_required_tools

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

    # A benchmark graded by an LLM judge needs a resolvable judge model (the
    # judge reuses the user's active model config). Without one every task in
    # both arms fails with a misleading all-zero comparison.
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

    # Re-check after the (potentially slow) embedding probe: two concurrent
    # requests can both pass the pre-probe guard, and only the probe keeps
    # the window open long enough to matter. The re-check is synchronous, so
    # the following _init_memory_ab_state cannot be interleaved.
    post_probe_status = get_memory_ab_status()
    if post_probe_status.get("is_running"):
        return {"status": "already_running", "info": post_probe_status}

    # Mark state as running synchronously before the response is sent (same
    # race guard as the benchmark run flow: BackgroundTasks start after the
    # response, so the SSE stream would otherwise read a stale idle frame).
    _init_memory_ab_state(request.benchmark_id)
    background_tasks.add_task(
        run_memory_ab_background,
        benchmark_id=request.benchmark_id,
        profile_id=request.profile_id,
        limit=request.limit,
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


@router.get("/memory-ab/stream")
async def stream_memory_ab_evaluation_status() -> StreamingResponse:
    """Stream the current status of the memory A/B evaluation via SSE."""
    return StreamingResponse(
        stream_status_events(get_memory_ab_status),
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
