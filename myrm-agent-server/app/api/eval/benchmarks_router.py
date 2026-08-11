"""External Benchmarks API Router — unified catalog + run/download endpoints.

[INPUT]
- fastapi::APIRouter, BackgroundTasks
- app.core.eval.service::get_eval_status, run_benchmark_background,
  run_benchmark_download_background, run_wb_bench_background,
  run_wb_bench_download_background
- app.core.eval.benchmarks::list_benchmark_sources, is_known_benchmark
- app.core.eval.wb_bench::list_wb_bench_sources, WB_BENCH_SUBSETS

[OUTPUT]
- router: APIRouter mounted under /eval (included by app.api.eval.router).

[POS]
HTTP layer for external benchmarks (WBBench subsets + registered
third-party). Kept as a self-contained sub-router so the main eval router
stays focused on the single-profile eval, datasets, cases, and reports.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.core.eval.benchmarks import is_known_benchmark, list_benchmark_sources
from app.core.eval.service import (
    _init_benchmark_state,
    _init_wb_bench_state,
    get_eval_status,
    run_benchmark_background,
    run_benchmark_download_background,
    run_wb_bench_background,
    run_wb_bench_download_background,
)
from app.core.eval.wb_bench import WB_BENCH_SUBSETS, list_wb_bench_sources

router = APIRouter(tags=["eval"])


@router.get("/benchmarks")
async def list_benchmarks() -> dict[str, object]:
    """List all external benchmarks (WBBench subsets + registered third-party)."""
    return {"status": "success", "sources": list_benchmark_sources()}


class BenchmarkRunRequest(BaseModel):
    benchmark_id: str
    profile_id: str | None = None
    benchmark_mode: bool = False


class BenchmarkDownloadRequest(BaseModel):
    benchmark_id: str


@router.post("/benchmarks/run")
async def run_benchmark(
    background_tasks: BackgroundTasks,
    request: BenchmarkRunRequest,
) -> dict[str, object]:
    """Download (if needed) and run an external benchmark in the background."""
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    if not is_known_benchmark(request.benchmark_id):
        return {
            "status": "error",
            "error": f"Unknown benchmark: {request.benchmark_id}",
        }

    # Mark the eval state as running synchronously before the response is sent.
    # FastAPI BackgroundTasks run only after the response, so the SSE stream the
    # frontend opens on "started" would otherwise read a stale is_running=false
    # first frame and immediately drop the running flag (race on run start).
    _init_benchmark_state(request.benchmark_id)
    background_tasks.add_task(
        run_benchmark_background,
        benchmark_id=request.benchmark_id,
        profile_id=request.profile_id,
        benchmark_mode=request.benchmark_mode,
        stage_label=request.benchmark_id,
    )
    return {"status": "started"}


@router.post("/benchmarks/download")
async def download_benchmark(
    background_tasks: BackgroundTasks,
    request: BenchmarkDownloadRequest,
) -> dict[str, object]:
    """Download an external benchmark in the background without running it.

    Lets users pre-fetch large archives (e.g. the ~480 MB WBBench Security
    subset) and surface the download status before starting a benchmark run.
    """
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    if not is_known_benchmark(request.benchmark_id):
        return {
            "status": "error",
            "error": f"Unknown benchmark: {request.benchmark_id}",
        }

    _init_benchmark_state(request.benchmark_id)
    background_tasks.add_task(
        run_benchmark_download_background,
        benchmark_id=request.benchmark_id,
        stage_label=request.benchmark_id,
    )
    return {"status": "started"}


@router.get("/wb-bench/sources")
async def list_wb_bench_sources_endpoint() -> dict[str, object]:
    """List the WorkBuddy Bench subsets with local download status."""
    return {"status": "success", "sources": list_wb_bench_sources()}


class WbBenchRunRequest(BaseModel):
    subset_id: str
    profile_id: str | None = None
    benchmark_mode: bool = False


class WbBenchDownloadRequest(BaseModel):
    subset_id: str


@router.post("/wb-bench/run")
async def run_wb_bench(
    background_tasks: BackgroundTasks,
    request: WbBenchRunRequest,
) -> dict[str, object]:
    """Download (if needed) and run a WorkBuddy Bench subset in the background.

    Legacy endpoint; delegates to the unified benchmark run flow.
    """
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    if request.subset_id not in WB_BENCH_SUBSETS:
        return {
            "status": "error",
            "error": f"Unknown WBBench subset: {request.subset_id}",
        }

    # Mark the eval state as running synchronously before the response is sent.
    # FastAPI BackgroundTasks run only after the response, so the SSE stream the
    # frontend opens on "started" would otherwise read a stale is_running=false
    # first frame and immediately drop the running flag (race on run start).
    _init_wb_bench_state(request.subset_id)
    background_tasks.add_task(
        run_wb_bench_background,
        subset_id=request.subset_id,
        profile_id=request.profile_id,
        benchmark_mode=request.benchmark_mode,
    )
    return {"status": "started"}


@router.post("/wb-bench/download")
async def download_wb_bench(
    background_tasks: BackgroundTasks,
    request: WbBenchDownloadRequest,
) -> dict[str, object]:
    """Download a WorkBuddy Bench subset in the background without running it.

    Legacy endpoint; delegates to the unified benchmark download flow. Lets
    users pre-fetch large archives (e.g. the ~480 MB Security subset) and
    surface the download status before starting a benchmark run.
    """
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    if request.subset_id not in WB_BENCH_SUBSETS:
        return {
            "status": "error",
            "error": f"Unknown WBBench subset: {request.subset_id}",
        }

    _init_wb_bench_state(request.subset_id)
    background_tasks.add_task(
        run_wb_bench_download_background,
        subset_id=request.subset_id,
    )
    return {"status": "started"}
