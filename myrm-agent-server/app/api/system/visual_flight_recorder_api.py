"""
[INPUT]: Visual capture frames, slice capture triggers, and query filters.
[OUTPUT]: REST API endpoints for rolling ring-buffer visual flight recording and failure slice playback.
[POS]: myrm-agent/myrm-agent-server/app/api/system/visual_flight_recorder_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.visual_flight_recorder import (
    VisualFailureSlice,
    VisualFrame,
    get_default_visual_flight_recorder,
)

router = APIRouter(prefix="/visual-flight-recorder", tags=["visual-flight-recorder"])


# --- Schemas ---


class VisualFrameModel(BaseModel):
    frame_index: int = Field(..., ge=0, description="Sequential frame index")
    timestamp_ms: int = Field(..., ge=0, description="Epoch timestamp of capture")
    image_data_uri: str = Field(..., description="Data URI or local resource URI of the frame image")
    width: int = Field(default=1280, ge=1, description="Frame width in pixels")
    height: int = Field(default=720, ge=1, description="Frame height in pixels")
    dom_event_summary: str = Field(default="", description="DOM or input event occurred during frame")


class PushFrameRequest(BaseModel):
    frame: VisualFrameModel


class CaptureSliceRequest(BaseModel):
    trace_id: str = Field(..., description="Correlated execution trace ID")
    session_id: str = Field(..., description="Correlated session identifier")
    failure_kind: str = Field(..., description="Failure category: popup_overlay, captcha_slider, element_timeout, stuck_loop, crash")
    root_cause_label: str = Field(..., description="Actionable human-readable root cause explanation")
    animated_preview_uri: str = Field(default="", description="Optional URI to stitched WebP/GIF animation")
    custom_slice_id: Optional[str] = Field(default=None, description="Optional custom slice ID")


class VisualFailureSliceModel(BaseModel):
    slice_id: str
    trace_id: str
    session_id: str
    failure_kind: str
    root_cause_label: str
    total_frames: int
    duration_seconds: float
    frames: List[VisualFrameModel]
    animated_preview_uri: str
    created_at_ms: int


class StuckStatusResponse(BaseModel):
    is_stuck: bool
    current_buffer_size: int
    max_frames: int


# --- Helper Converters ---


def _to_slice_model(s: VisualFailureSlice) -> VisualFailureSliceModel:
    return VisualFailureSliceModel(
        slice_id=s.slice_id,
        trace_id=s.trace_id,
        session_id=s.session_id,
        failure_kind=s.failure_kind,
        root_cause_label=s.root_cause_label,
        total_frames=s.total_frames,
        duration_seconds=s.duration_seconds,
        frames=[
            VisualFrameModel(
                frame_index=f.frame_index,
                timestamp_ms=f.timestamp_ms,
                image_data_uri=f.image_data_uri,
                width=f.width,
                height=f.height,
                dom_event_summary=f.dom_event_summary,
            )
            for f in s.frames
        ],
        animated_preview_uri=s.animated_preview_uri,
        created_at_ms=s.created_at_ms,
    )


# --- Endpoints ---


@router.post("/push-frame")
async def push_visual_frame(req: PushFrameRequest) -> Dict[str, bool]:
    """Append a visual frame to the rolling in-memory ring buffer."""
    recorder = get_default_visual_flight_recorder()
    frame = VisualFrame(
        frame_index=req.frame.frame_index,
        timestamp_ms=req.frame.timestamp_ms,
        image_data_uri=req.frame.image_data_uri,
        width=req.frame.width,
        height=req.frame.height,
        dom_event_summary=req.frame.dom_event_summary,
    )
    recorder.push_frame(frame)
    return {"ok": True}


@router.post("/capture-slice", response_model=VisualFailureSliceModel)
async def capture_failure_slice(req: CaptureSliceRequest) -> VisualFailureSliceModel:
    """Seal the current rolling buffer into an immutable failure slice upon crash or stuck state."""
    recorder = get_default_visual_flight_recorder()
    slice_rec = recorder.capture_failure_slice(
        trace_id=req.trace_id,
        session_id=req.session_id,
        failure_kind=req.failure_kind,
        root_cause_label=req.root_cause_label,
        animated_preview_uri=req.animated_preview_uri,
        custom_slice_id=req.custom_slice_id,
    )
    return _to_slice_model(slice_rec)


@router.get("/slice/{slice_id}", response_model=VisualFailureSliceModel)
async def get_failure_slice(slice_id: str) -> VisualFailureSliceModel:
    """Fetch archived visual failure slice and frame filmstrip by slice ID."""
    recorder = get_default_visual_flight_recorder()
    slice_rec = recorder.get_slice(slice_id)
    if slice_rec is None:
        raise HTTPException(status_code=404, detail="Visual failure slice not found")
    return _to_slice_model(slice_rec)


@router.get("/slices", response_model=List[VisualFailureSliceModel])
async def list_failure_slices(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    failure_kind: Optional[str] = Query(None, description="Filter by failure category"),
    limit: int = Query(20, ge=1, le=100, description="Max slice records to return"),
) -> List[VisualFailureSliceModel]:
    """List archived failure slices, newest first."""
    recorder = get_default_visual_flight_recorder()
    slices = recorder.list_slices(session_id=session_id, failure_kind=failure_kind, limit=limit)
    return [_to_slice_model(s) for s in slices]


@router.get("/stuck-status", response_model=StuckStatusResponse)
async def get_stuck_status() -> StuckStatusResponse:
    """Check if the current visual buffer indicates a stagnant or stuck state."""
    recorder = get_default_visual_flight_recorder()
    return StuckStatusResponse(
        is_stuck=recorder.detect_visual_stuck(),
        current_buffer_size=recorder.current_buffer_size(),
        max_frames=recorder.config.max_frames,
    )


@router.post("/reset")
async def reset_flight_recorder() -> Dict[str, bool]:
    """Clear visual ring buffer and all archived failure slices."""
    recorder = get_default_visual_flight_recorder()
    recorder.reset()
    return {"ok": True}
