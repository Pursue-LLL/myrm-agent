"""
[INPUT]: Decoupled multimodal media registrations, 3-step diagnostic traces, and Golden Eval requests.
[OUTPUT]: Pydantic schemas and REST endpoints for decoupled multimodal trace media references and in-place inspection.
[POS]: myrm-agent/myrm-agent-server/app/api/system/multimodal_trace_api.py
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.multimodal_trace import (
    MediaModality,
    MediaReference,
    MediaVisibilityState,
    MultimodalStepType,
    MultimodalTraceRecord,
    MultimodalTraceStep,
    get_default_multimodal_trace_manager,
)

router = APIRouter(prefix="/multimodal-trace", tags=["multimodal-trace"])


# --- Pydantic Request & Response Schemas ---


class RegisterMediaRequest(BaseModel):
    media_id: str = Field(..., description="Unique media reference ID")
    uri: str = Field(..., description="Storage volume path or object store URI")
    modality: str = Field(default="image", description="image, audio, video, document")
    mime_type: str = Field(default="image/png", description="MIME content type")
    file_size_bytes: int = Field(default=0, ge=0, description="Binary file size in bytes")
    sha256_hash: str = Field(..., description="Cryptographic SHA256 content checksum")
    presigned_preview_url: str = Field(default="", description="Temporary secured presigned preview URL")
    visibility_state: str = Field(default="ready", description="ready, uploading, expired, purged")


class UpdateVisibilityRequest(BaseModel):
    media_id: str = Field(..., description="Target media reference ID")
    visibility_state: str = Field(..., description="New visibility state: ready, uploading, expired, purged")
    presigned_preview_url: Optional[str] = Field(default=None, description="Optional updated presigned URL")


class TraceStepInputModel(BaseModel):
    step_index: int = Field(..., ge=1, description="Sequential step index")
    step_type: str = Field(default="input", description="input, execution, feedback")
    description: str = Field(..., description="Human or agent explanation of the step")
    media_ids: List[str] = Field(default_factory=list, description="Associated media IDs")
    status: str = Field(default="success", description="success, failed, skipped")


class RecordTraceRequest(BaseModel):
    trace_id: str = Field(..., description="Unique multimodal trace ID")
    session_id: str = Field(..., description="Parent session ID")
    prompt_summary: str = Field(..., description="High-level prompt summary")
    media_ids: List[str] = Field(default_factory=list, description="Referenced media IDs")
    steps: List[TraceStepInputModel] = Field(default_factory=list, description="3-step inspection stages")


class PinGoldenEvalRequest(BaseModel):
    category: str = Field(default="visual_regression", description="Evaluation category label")


class MediaReferenceModel(BaseModel):
    media_id: str
    uri: str
    modality: str
    mime_type: str
    file_size_bytes: int
    sha256_hash: str
    visibility_state: str
    presigned_preview_url: str
    created_at_ms: int


class MultimodalTraceStepModel(BaseModel):
    step_index: int
    step_type: str
    description: str
    media_ids: List[str]
    status: str
    timestamp_ms: int


class MultimodalTraceRecordModel(BaseModel):
    trace_id: str
    session_id: str
    prompt_summary: str
    media_references: List[MediaReferenceModel]
    steps: List[MultimodalTraceStepModel]
    pinned_for_golden_eval: bool
    golden_eval_category: str
    created_at_ms: int


# --- Helper Converters ---


def _to_media_model(ref: MediaReference) -> MediaReferenceModel:
    return MediaReferenceModel(
        media_id=ref.media_id,
        uri=ref.uri,
        modality=ref.modality.value,
        mime_type=ref.mime_type,
        file_size_bytes=ref.file_size_bytes,
        sha256_hash=ref.sha256_hash,
        visibility_state=ref.visibility_state.value,
        presigned_preview_url=ref.presigned_preview_url,
        created_at_ms=ref.created_at_ms,
    )


def _to_step_model(s: MultimodalTraceStep) -> MultimodalTraceStepModel:
    return MultimodalTraceStepModel(
        step_index=s.step_index,
        step_type=s.step_type.value,
        description=s.description,
        media_ids=list(s.media_ids),
        status=s.status,
        timestamp_ms=s.timestamp_ms,
    )


def _to_trace_model(t: MultimodalTraceRecord) -> MultimodalTraceRecordModel:
    return MultimodalTraceRecordModel(
        trace_id=t.trace_id,
        session_id=t.session_id,
        prompt_summary=t.prompt_summary,
        media_references=[_to_media_model(m) for m in t.media_references],
        steps=[_to_step_model(s) for s in t.steps],
        pinned_for_golden_eval=t.pinned_for_golden_eval,
        golden_eval_category=t.golden_eval_category,
        created_at_ms=t.created_at_ms,
    )


# --- Endpoints ---


@router.post("/register-media", response_model=MediaReferenceModel)
async def register_media(req: RegisterMediaRequest) -> MediaReferenceModel:
    """Register lightweight decoupled media reference."""
    manager = get_default_multimodal_trace_manager()
    ref = manager.register_media(
        media_id=req.media_id,
        uri=req.uri,
        modality=req.modality,
        mime_type=req.mime_type,
        file_size_bytes=req.file_size_bytes,
        sha256_hash=req.sha256_hash,
        presigned_preview_url=req.presigned_preview_url,
        visibility_state=req.visibility_state,
    )
    return _to_media_model(ref)


@router.post("/update-visibility")
async def update_media_visibility(req: UpdateVisibilityRequest) -> Dict[str, bool]:
    """Update media visibility lifecycle or refresh presigned URL."""
    manager = get_default_multimodal_trace_manager()
    ok = manager.update_media_visibility(
        media_id=req.media_id,
        visibility_state=req.visibility_state,
        presigned_preview_url=req.presigned_preview_url,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Media reference not found")
    return {"ok": True}


@router.post("/record-trace", response_model=MultimodalTraceRecordModel)
async def record_multimodal_trace(req: RecordTraceRequest) -> MultimodalTraceRecordModel:
    """Record multimodal execution trace with 3-step inspection stages."""
    manager = get_default_multimodal_trace_manager()
    steps: list[MultimodalTraceStep] = []
    for s in req.steps:
        try:
            stype = MultimodalStepType(s.step_type.strip().lower())
        except ValueError:
            stype = MultimodalStepType.INPUT

        steps.append(
            MultimodalTraceStep(
                step_index=s.step_index,
                step_type=stype,
                description=s.description,
                media_ids=tuple(s.media_ids),
                status=s.status,
            )
        )

    record = manager.record_trace(
        trace_id=req.trace_id,
        session_id=req.session_id,
        prompt_summary=req.prompt_summary,
        media_ids=req.media_ids,
        steps=steps,
    )
    return _to_trace_model(record)


@router.post("/pin/{trace_id}")
async def pin_trace_for_golden_eval(trace_id: str, req: Optional[PinGoldenEvalRequest] = None) -> Dict[str, bool]:
    """Lock trace and its media assets as Golden Eval sample, preventing TTL cleanup."""
    manager = get_default_multimodal_trace_manager()
    cat = req.category if req else "visual_regression"
    ok = manager.pin_trace_for_golden_eval(trace_id=trace_id, category=cat)
    if not ok:
        raise HTTPException(status_code=404, detail="Trace record not found")
    return {"ok": True}


@router.get("/trace/{trace_id}", response_model=MultimodalTraceRecordModel)
async def get_multimodal_trace(trace_id: str) -> MultimodalTraceRecordModel:
    """Fetch full multimodal trace details by ID."""
    manager = get_default_multimodal_trace_manager()
    trace = manager.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return _to_trace_model(trace)


@router.get("/traces", response_model=List[MultimodalTraceRecordModel])
async def list_multimodal_traces(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    modality: Optional[str] = Query(None, description="Filter by media modality (image, audio, video, document)"),
    pinned_only: bool = Query(False, description="Filter only pinned golden eval samples"),
    limit: int = Query(50, ge=1, le=200, description="Max traces to return"),
) -> List[MultimodalTraceRecordModel]:
    """Query multimodal traces."""
    manager = get_default_multimodal_trace_manager()
    traces = manager.list_traces(
        session_id=session_id,
        modality=modality,
        pinned_only=pinned_only,
        limit=limit,
    )
    return [_to_trace_model(t) for t in traces]


@router.post("/reset")
async def reset_multimodal_traces() -> Dict[str, bool]:
    """Reset multimodal trace records and media references."""
    manager = get_default_multimodal_trace_manager()
    manager.reset()
    return {"ok": True}
