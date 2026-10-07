"""[POS]: app/api/memory/context_ingestion.py
[INPUT]: HTTP requests for multi-source context ingestion and Plaud hardware voice synchronization.
[OUTPUT]: FastAPI APIRouter endpoints managing universal transcript parsing, dedup, and distillation.
"""

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import (
    ContextIngestionPayload,
    IngestionSourceType,
    UniversalContextIngestionGateway,
)

from app.schemas.context_ingestion import (
    IngestContextRequest,
    IngestContextResponse,
    IngestionHistoryItem,
    IngestionHistoryResponse,
    PlaudWebhookRequest,
    SupportedFormatsResponse,
)
from app.services.memory.context_ingestion import get_context_ingestion_gateway

router = APIRouter(prefix="/ingestion", tags=["context_ingestion"])


@router.post("/ingest", response_model=IngestContextResponse)
def ingest_context(
    req: IngestContextRequest,
    gateway: UniversalContextIngestionGateway = Depends(get_context_ingestion_gateway),
) -> IngestContextResponse:
    """Ingest multi-source context transcript with automatic deduplication and distillation."""
    source_enum = (
        IngestionSourceType(req.source_type)
        if req.source_type in [s.value for s in IngestionSourceType]
        else IngestionSourceType.RAW_TRANSCRIPT
    )
    payload = ContextIngestionPayload(
        source_type=source_enum,
        device_id=req.device_id,
        title=req.title,
        raw_payload=req.raw_payload,
        session_id=req.session_id,
        metadata=req.metadata,
    )
    res = gateway.ingest(payload)
    return IngestContextResponse(
        fingerprint=res.fingerprint,
        title=res.title,
        source_type=res.source_type,
        speaker_count=res.speaker_count,
        segment_count=res.segment_count,
        summary=res.summary,
        action_items=res.action_items,
        decisions=res.decisions,
        is_duplicate=res.is_duplicate,
        created_at_epoch=res.created_at_epoch,
    )


@router.post("/webhook/plaud", response_model=IngestContextResponse)
def plaud_webhook_sync(
    req: PlaudWebhookRequest,
    gateway: UniversalContextIngestionGateway = Depends(get_context_ingestion_gateway),
) -> IngestContextResponse:
    """Webhook listener for Plaud hardware voice recorder card sync events."""
    payload = ContextIngestionPayload(
        source_type=IngestionSourceType.PLAUD_VOICE_CARD,
        device_id=req.device_id,
        title=req.meeting_title,
        raw_payload=req.transcription_json,
        metadata=req.tags,
    )
    res = gateway.ingest(payload)
    return IngestContextResponse(
        fingerprint=res.fingerprint,
        title=res.title,
        source_type=res.source_type,
        speaker_count=res.speaker_count,
        segment_count=res.segment_count,
        summary=res.summary,
        action_items=res.action_items,
        decisions=res.decisions,
        is_duplicate=res.is_duplicate,
        created_at_epoch=res.created_at_epoch,
    )


@router.get("/history", response_model=IngestionHistoryResponse)
def get_ingestion_history(
    limit: int = 50,
    gateway: UniversalContextIngestionGateway = Depends(get_context_ingestion_gateway),
) -> IngestionHistoryResponse:
    """Retrieve history of recently ingested voice records."""
    records = gateway.list_history(limit=limit)
    items = [
        IngestionHistoryItem(
            fingerprint=str(r["fingerprint"]),
            source_type=str(r["source_type"]),
            device_id=str(r["device_id"]),
            title=str(r["title"]),
            created_at_epoch=float(r["created_at_epoch"]),
        )
        for r in records
    ]
    return IngestionHistoryResponse(items=items, total=len(items))


@router.get("/supported-formats", response_model=SupportedFormatsResponse)
def get_supported_formats() -> SupportedFormatsResponse:
    """List supported audio transcript formats and protocols."""
    formats = [s.value for s in IngestionSourceType]
    descriptions = {
        IngestionSourceType.PLAUD_VOICE_CARD.value: "Plaud hardware card exported JSON transcript",
        IngestionSourceType.WEBVTT.value: "Standard WebVTT subtitle cue format (.vtt)",
        IngestionSourceType.SRT.value: "SubRip subtitle format (.srt) with timestamps",
        IngestionSourceType.RAW_TRANSCRIPT.value: "Plain multi-speaker dialog or raw meeting notes",
        IngestionSourceType.WEBHOOK.value: "Cloud automated recording webhook payload",
    }
    return SupportedFormatsResponse(formats=formats, description=descriptions)
