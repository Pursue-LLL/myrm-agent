"""Eval API Router.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException
- app.core.eval.service::run_eval_suite, get_latest_report_summary

[OUTPUT]
- router: APIRouter for eval endpoints.

[POS]
Exposes the evaluation framework to the Frontend and Control Plane.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.eval.capture import capture_case_from_chat
from app.core.eval.service import (
    abort_eval,
    abort_matrix_eval,
    abort_memory_ab,
    get_all_report_summaries,
    get_eval_cases,
    get_eval_status,
    get_latest_matrix_report,
    get_latest_memory_ab_report,
    get_latest_report_summary,
    get_matrix_eval_status,
    get_memory_ab_report,
    get_memory_ab_report_history,
    get_memory_ab_status,
    run_eval_suite_background,
    run_matrix_eval_background,
    run_memory_ab_background,
    run_wb_bench_background,
    run_wb_bench_download_background,
    save_eval_cases,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])


class EvalCasesRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# WorkBuddy Bench — external benchmark dataset sources
# ---------------------------------------------------------------------------


@router.get("/wb-bench/sources")
async def list_wb_bench_sources() -> dict[str, object]:
    """List the WorkBuddy Bench subsets with local download status."""
    from app.core.eval.wb_bench import list_wb_bench_sources

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
    """Download (if needed) and run a WorkBuddy Bench subset in the background."""
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    from app.core.eval.service import _init_wb_bench_state
    from app.core.eval.wb_bench import WB_BENCH_SUBSETS

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

    Lets users pre-fetch large archives (e.g. the ~480 MB Security subset) and
    surface the download status before starting a benchmark run.
    """
    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    from app.core.eval.service import _init_wb_bench_state
    from app.core.eval.wb_bench import WB_BENCH_SUBSETS

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


@router.get("/datasets")
async def list_datasets() -> dict[str, object]:
    """Get all available evaluation datasets."""
    from app.core.eval.service import get_all_datasets

    datasets = get_all_datasets()
    return {"status": "success", "datasets": datasets}


@router.get("/datasets/{dataset_id}")
async def get_dataset_content(dataset_id: str) -> dict[str, object]:
    """Get the content of a specific dataset."""
    content = get_eval_cases(dataset_id)
    return {"status": "success", "content": content}


@router.put("/datasets/{dataset_id}")
async def update_dataset_content(
    dataset_id: str,
    request: EvalCasesRequest,
) -> dict[str, object]:
    """Update the content of a specific dataset."""
    success = save_eval_cases(request.content, dataset_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save dataset {dataset_id}",
        )
    return {"status": "success"}


@router.get("/cases")
async def get_cases() -> dict[str, object]:
    """Get the current evaluation cases (JSONL format)."""

    content = get_eval_cases()
    return {"status": "success", "content": content}


@router.put("/cases")
async def update_cases(
    request: EvalCasesRequest,
) -> dict[str, object]:
    """Update the evaluation cases."""

    success = save_eval_cases(request.content)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save evaluation cases",
        )
    return {"status": "success"}


@router.post("/cases/from-chat/{chat_id}")
async def capture_case(
    chat_id: str, dataset_id: str | None = None
) -> dict[str, object]:
    """Capture a chat session and append it to evaluation cases."""
    success = await capture_case_from_chat(chat_id, dataset_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to capture evaluation case from chat",
        )
    return {"status": "success"}


class RunEvalRequest(BaseModel):
    profile_id: str | None = None
    dataset_id: str | None = None
    benchmark_mode: bool = False


@router.post("/run")
async def run_evaluation(
    background_tasks: BackgroundTasks,
    request: RunEvalRequest | None = None,
) -> dict[str, object]:
    """Start the standard evaluation suite for the current user in the background."""

    status_info = get_eval_status()
    if status_info.get("is_running"):
        return {"status": "already_running", "info": status_info}

    profile_id = request.profile_id if request else None
    dataset_id = request.dataset_id if request else None
    benchmark_mode = request.benchmark_mode if request else False
    background_tasks.add_task(
        run_eval_suite_background,
        dataset_id=dataset_id,
        profile_id=profile_id,
        benchmark_mode=benchmark_mode,
    )
    return {"status": "started"}


@router.post("/abort")
async def abort_evaluation() -> dict[str, object]:
    """Abort the currently running evaluation suite."""
    success = abort_eval()
    if not success:
        return {"status": "not_running"}
    return {"status": "aborted"}


async def _eval_status_generator() -> AsyncGenerator[str, None]:
    last_state_str = ""
    while True:
        status_info = get_eval_status()
        current_state_str = json.dumps(status_info)
        if current_state_str != last_state_str:
            yield f"data: {current_state_str}\n\n"
            last_state_str = current_state_str

        if not status_info.get("is_running"):
            yield "event: close\ndata: {}\n\n"
            break

        await asyncio.sleep(0.5)


@router.get("/stream")
async def stream_evaluation_status() -> StreamingResponse:
    """Stream the current status of the evaluation suite via SSE."""
    return StreamingResponse(
        _eval_status_generator(),
        media_type="text/event-stream",
        headers=SSE_RESPONSE_HEADERS,
    )


@router.get("/status")
async def get_evaluation_status() -> dict[str, object]:
    """Get the current status of the evaluation suite."""
    return get_eval_status()


@router.get("/reports/latest")
async def get_latest_report() -> dict[str, object]:
    """Get the summary of the latest evaluation report."""

    summary = get_latest_report_summary()
    if not summary:
        return {"status": "not_found", "summary": None}

    return {"status": "success", "summary": summary}


@router.get("/reports")
async def get_all_reports() -> dict[str, object]:
    """Get all historical evaluation reports summaries."""
    summaries = get_all_report_summaries()
    return {"status": "success", "reports": summaries}


@router.get("/reports/{filename}")
async def get_specific_report(filename: str) -> dict[str, object]:
    """Get a specific historical evaluation report with full details."""
    if not filename.endswith(".jsonl") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    from app.core.eval.service import DEFAULT_REPORTS_DIR

    report_path = DEFAULT_REPORTS_DIR / filename
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        with report_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                raise HTTPException(status_code=404, detail="Report is empty")
            data = json.loads(lines[0])
            if data.get("type") == "summary":
                data["cases"] = []
                for line in lines[1:]:
                    if line.strip():
                        data["cases"].append(json.loads(line))
                return {"status": "success", "summary": data}
    except Exception as exc:
        logger.error("Eval result retrieval failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Eval result retrieval failed"
        ) from exc

    return {"status": "error"}


@router.get("/internal/metrics/eval", include_in_schema=False)
async def get_eval_metrics() -> dict[str, object]:
    """Internal endpoint for Control Plane to pull anonymized eval metrics."""
    summary = get_latest_report_summary()
    if not summary:
        return {"status": "not_found", "metrics": None}

    # Only return anonymized statistical data, no specific cases or user info
    metrics = {
        "total_cases": summary.get("total_cases"),
        "pass_rate": summary.get("pass_rate"),
        "pass_count": summary.get("pass_count"),
        "fail_count": summary.get("fail_count"),
        "error_count": summary.get("error_count"),
        "total_ms": summary.get("total_ms"),
    }
    return {"status": "success", "metrics": metrics}


# ---------------------------------------------------------------------------
# Matrix Eval — cross-profile comparison endpoints
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Memory A/B Eval — memory-on vs memory-off comparison endpoints
# ---------------------------------------------------------------------------


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

    from app.core.eval.service import _init_memory_ab_state
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
    from myrm_agent_harness.api import ConfigIncompleteError

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
