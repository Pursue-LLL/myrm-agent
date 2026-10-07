"""FastAPI router for Listen-Translate-Remember-Act (LTRA) cognitive pipeline.

[POS]
随身感知“听—译—记—办” HTTP 接入层。暴露录音转写摄入、事实四元组查询、
自然语言追问与原话毫秒引用、HTTP 206 音频切片流式回放以及一键沙箱派发端点。

[INPUT]
- app.schemas.ltra_cognitive DTOs
- app.services.memory.ltra::get_ltra_service

[OUTPUT]
- router: LTRA 认知感知流转与派办 REST 路由
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.schemas.ltra_cognitive import (
    CognitiveFactDTO,
    DispatchedTaskResponse,
    FactDistillResponse,
    FollowupQueryRequest,
    FollowupQueryResponse,
    IngestAudioTranscriptRequest,
    TaskDispatchPlanRequest,
)
from app.services.memory.ltra import get_ltra_service

router = APIRouter(prefix="/ltra", tags=["memory-ltra-cognitive"])


@router.post(
    "/ingest-transcript",
    response_model=FactDistillResponse,
    summary="Ingest diarized transcript and distill cognitive fact quadruples",
)
def ingest_transcript(request: IngestAudioTranscriptRequest) -> FactDistillResponse:
    """Process multi-turn speech segments and persist distilled facts."""
    service = get_ltra_service()
    return service.ingest_transcript(request)


@router.get(
    "/facts",
    response_model=list[CognitiveFactDTO],
    summary="List stored cognitive facts with optional filters",
)
def list_facts(
    project_id: str | None = Query(default=None, description="Filter by project id"),
    target_agent_id: str | None = Query(default=None, description="Filter by agent id"),
) -> list[CognitiveFactDTO]:
    """Retrieve all facts matching scope criteria."""
    service = get_ltra_service()
    return service.list_facts(project_id=project_id, target_agent_id=target_agent_id)


@router.post(
    "/query-and-cite",
    response_model=FollowupQueryResponse,
    summary="Query facts by natural language question and receive verbatim citation",
)
def query_and_cite(request: FollowupQueryRequest) -> FollowupQueryResponse:
    """Match natural language inquiry against stored facts and return audio anchors."""
    service = get_ltra_service()
    return service.query_and_cite(
        query=request.query,
        project_id=request.project_id,
        target_agent_id=request.target_agent_id,
    )


@router.post(
    "/dispatch-task",
    response_model=DispatchedTaskResponse,
    summary="Dispatch confirmed fact as actionable sandbox task blueprint",
)
def dispatch_task(request: TaskDispatchPlanRequest) -> DispatchedTaskResponse:
    """Generate sandbox task specification and trigger agent execution."""
    service = get_ltra_service()
    try:
        return service.dispatch_task(request)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.get(
    "/audio/{audio_id}/clip",
    summary="Stream audio slice bytes with HTTP 206 Partial Content",
)
def stream_audio_clip(
    audio_id: str,
    start_ms: int = Query(default=0, ge=0, description="Start offset in milliseconds"),
    end_ms: int = Query(default=5000, ge=1, description="End offset in milliseconds"),
) -> Response:
    """Stream slice of recorded conversation for instant verbatim playback in GUI."""
    if end_ms <= start_ms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_ms must be strictly greater than start_ms",
        )

    service = get_ltra_service()
    clip_bytes, start_byte, end_byte, total_bytes = service.get_audio_clip(
        audio_id=audio_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )

    content_range = f"bytes {start_byte}-{end_byte}/{total_bytes}"
    headers = {
        "Content-Range": content_range,
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(clip_bytes)),
    }

    return Response(
        content=clip_bytes,
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type="audio/wav",
        headers=headers,
    )
