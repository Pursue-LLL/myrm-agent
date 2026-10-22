"""Run State Multi-Surface Projection API Router.

[INPUT]
- SurfaceViewType, RunStateSnapshot, RunProjectionEvent, AttemptRecord
- run_projection_service singleton

[OUTPUT]
- projection_router: APIRouter for pure functional run projections and attempt inspection

[POS]
app/api/runs/projection_router.py: REST endpoints for multi-surface projection
(Chat, Runtime Console, Deliverables, Audit), attempt watermarks, and monotonic events.
"""

from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.services.runs.projection import (
    AttemptRecord,
    RunProjectionEvent,
    RunStateSnapshot,
    SurfaceViewType,
    run_projection_service,
)

projection_router = APIRouter(prefix="/runs", tags=["Run State Multi-Surface Projection"])


class SwitchSurfaceRequest(BaseModel):
    """Payload to switch active projection surface viewport."""

    surface: SurfaceViewType = Field(..., description="Target projection surface")


class CreateAttemptRequest(BaseModel):
    """Payload to record a new execution attempt."""

    attempt_number: int = Field(..., ge=1, description="Sequence number of attempt")
    status: Literal["pending", "executing", "completed", "failed", "retrying"] = Field(
        default="executing", description="Attempt status"
    )
    tokens_in: int = Field(default=0, ge=0, description="Input tokens")
    tokens_out: int = Field(default=0, ge=0, description="Output tokens")
    tokens_per_sec: float = Field(default=0.0, ge=0.0, description="Tokens per second")
    duration_ms: int | None = Field(default=None, description="Execution duration in ms")
    error_reason: str | None = Field(default=None, description="Error reason if failed")
    stack_trace: str | None = Field(default=None, description="Diagnostic stack trace")
    diff_summary: str | None = Field(default=None, description="Virtual diff summary")


@projection_router.get(
    "/{run_id}/projection",
    response_model=RunStateSnapshot,
    status_code=status.HTTP_200_OK,
    summary="Get immutable pure functional state snapshot of a Run",
)
def get_run_projection(run_id: str) -> RunStateSnapshot:
    """Fetch complete RunStateSnapshot for multi-surface projection."""
    snapshot = run_projection_service.get_run_projection(run_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in projection store",
        )
    return snapshot


@projection_router.get(
    "/{run_id}/events",
    response_model=list[RunProjectionEvent],
    status_code=status.HTTP_200_OK,
    summary="Get monotonic event stream for a Run",
)
def get_run_events(
    run_id: str,
    since_ms: int = Query(default=0, ge=0, description="Filter events after timestamp in ms"),
) -> list[RunProjectionEvent]:
    """Retrieve event timeline since specified epoch watermark."""
    return run_projection_service.get_run_events(run_id, since_timestamp_ms=since_ms)


@projection_router.post(
    "/{run_id}/switch-surface",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
    summary="Switch active projection surface",
)
def switch_run_surface(run_id: str, req: SwitchSurfaceRequest) -> dict[str, str]:
    """Update focused surface across Chat, Runtime Console, Deliverables, and Audit."""
    success = run_projection_service.switch_surface(run_id, req.surface)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in projection store",
        )
    return {"status": "ok", "active_surface": req.surface}


@projection_router.post(
    "/{run_id}/attempts",
    response_model=AttemptRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new execution attempt with telemetry and fault diagnostics",
)
def record_run_attempt(run_id: str, req: CreateAttemptRequest) -> AttemptRecord:
    """Record attempt state transition and update run watermark."""
    return run_projection_service.record_attempt(
        run_id=run_id,
        attempt_number=req.attempt_number,
        status=req.status,
        tokens_in=req.tokens_in,
        tokens_out=req.tokens_out,
        tokens_per_sec=req.tokens_per_sec,
        duration_ms=req.duration_ms,
        error_reason=req.error_reason,
        stack_trace=req.stack_trace,
        diff_summary=req.diff_summary,
    )
