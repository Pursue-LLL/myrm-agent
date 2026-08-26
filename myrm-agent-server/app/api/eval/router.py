"""Eval API Router.

[INPUT]
- fastapi::APIRouter, Depends, HTTPException
- app.api.eval.streaming::stream_status_events (POS: eval SSE 状态流公共 helper)
- app.core.eval.service::run_eval_suite, get_eval_status, ...
- app.core.eval.datasets::get_eval_cases, save_eval_cases, get_all_datasets
- app.core.eval.reports::DEFAULT_REPORTS_DIR, get_latest_report_summary, ...
- app.api.eval.matrix_router / app.api.eval.memory_ab_router: sub-routers

[OUTPUT]
- router: APIRouter for eval endpoints (includes matrix + memory-ab sub-routers).

[POS]
Exposes the evaluation framework to the Frontend and Control Plane. Aggregates
the single-profile eval, WorkBuddy Bench, matrix, and memory A/B endpoints
under the /eval prefix.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse
from myrm_agent_harness.eval import (
    CANARY_GUID,
    EvalCanaryGate,
    embed_canary_header,
)
from pydantic import BaseModel

from app.api.eval.benchmarks_router import router as benchmarks_router
from app.api.eval.matrix_router import router as matrix_router
from app.api.eval.memory_ab_router import router as memory_ab_router
from app.api.eval.skill_ab_router import router as skill_ab_router
from app.api.eval.streaming import stream_status_events
from app.core.eval.capture import capture_case_from_chat
from app.core.eval.datasets import (
    get_all_datasets,
    get_eval_cases,
    save_eval_cases,
)
from app.core.eval.reports import (
    get_all_report_summaries,
    get_latest_report_summary,
)
from app.core.eval.service import (
    abort_eval,
    get_eval_status,
    run_eval_suite_background,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])

router.include_router(matrix_router)
router.include_router(memory_ab_router)
router.include_router(skill_ab_router)
router.include_router(benchmarks_router)


class EvalCasesRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Datasets & cases
# ---------------------------------------------------------------------------


@router.get("/datasets")
async def list_datasets() -> dict[str, object]:
    """Get all available evaluation datasets."""
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


@router.get("/stream")
async def stream_evaluation_status() -> StreamingResponse:
    """Stream the current status of the evaluation suite via SSE."""
    return StreamingResponse(
        stream_status_events(get_eval_status),
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

    from app.core.eval.reports import DEFAULT_REPORTS_DIR

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
    except HTTPException:
        raise
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


class CanaryEmbedRequest(BaseModel):
    content: str


@router.get("/anti-contamination/audit")
async def audit_anti_contamination(dataset_id: str | None = None) -> dict[str, object]:
    """Audit benchmark datasets against anti-contamination canary standards."""
    raw_content = get_eval_cases(dataset_id)
    scan_result = EvalCanaryGate.audit_dataset(raw_content)
    return {
        "status": "success",
        "dataset_id": dataset_id or "default",
        "is_protected": scan_result.is_protected,
        "canary_found": scan_result.canary_found,
        "canary_guid": CANARY_GUID,
        "violations": scan_result.violations,
        "metadata": scan_result.metadata,
    }


@router.post("/anti-contamination/embed-canary")
async def embed_canary(request: CanaryEmbedRequest) -> dict[str, object]:
    """Prepend standard anti-contamination canary header to raw dataset content."""
    protected_content = embed_canary_header(request.content)
    return {
        "status": "success",
        "protected_content": protected_content,
        "canary_guid": CANARY_GUID,
    }
