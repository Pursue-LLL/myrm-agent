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
    get_all_report_summaries,
    get_eval_cases,
    get_eval_status,
    get_latest_report_summary,
    run_eval_suite_background,
    save_eval_cases,
)
from app.schemas.streaming import SSE_RESPONSE_HEADERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["eval"])


class EvalCasesRequest(BaseModel):
    content: str


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
async def capture_case(chat_id: str, dataset_id: str | None = None) -> dict[str, object]:
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
    background_tasks.add_task(run_eval_suite_background, dataset_id=dataset_id, profile_id=profile_id)
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc

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
