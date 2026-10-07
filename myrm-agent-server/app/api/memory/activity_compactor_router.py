"""API router for Hierarchical Time-Window Activity Compactor pipeline.

[INPUT]
- Internal: app.schemas.activity_compactor, app.services.memory.activity_compactor_service
- External: fastapi

[OUTPUT]
- router: APIRouter handling activity ingestion, micro folding, macro distillation, and telemetry.

[POS]
Server API layer for Topic 01 Item 87 (ChatGPT Desktop Skysight-style 10min/6h/24h compaction).
"""

from fastapi import APIRouter, Query, status

from app.schemas.activity_compactor import (
    CompactorPipelineTelemetryDTO,
    DailyPreferenceArchiveDTO,
    IngestActivityEventRequestDTO,
    MacroMilestoneFoldDTO,
    MicroActivitySliceDTO,
    SynthesizeDailyArchiveRequestDTO,
    TriggerMacroDistillRequestDTO,
    TriggerMicroFoldRequestDTO,
)
from app.services.memory.activity_compactor_service import (
    get_activity_compactor_service,
)

router = APIRouter(prefix="/activity-compactor", tags=["memory-activity-compactor"])


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a raw desktop or terminal activity observation event",
)
def ingest_event(req: IngestActivityEventRequestDTO) -> dict[str, str]:
    """Stream incoming desktop or terminal observation event into the raw buffer."""
    service = get_activity_compactor_service()
    service.ingest_event(req)
    return {"status": "ok", "app_name": req.app_name}


@router.post(
    "/micro-fold",
    response_model=MicroActivitySliceDTO,
    summary="Trigger algorithmic 10-minute micro window fold (0 LLM Token cost)",
)
def trigger_micro_fold(
    req: TriggerMicroFoldRequestDTO | None = None,
) -> MicroActivitySliceDTO:
    """Flush the raw buffer into a 10-minute micro slice via pure algorithmic debouncing."""
    service = get_activity_compactor_service()
    return service.flush_micro_fold()


@router.post(
    "/macro-distill",
    response_model=MacroMilestoneFoldDTO,
    summary="Trigger 6-hour macro milestone distillation from aggregated micro slices",
)
def trigger_macro_distill(
    req: TriggerMacroDistillRequestDTO | None = None,
) -> MacroMilestoneFoldDTO:
    """Distill recent micro activity slices into a 6-hour business milestone fold."""
    service = get_activity_compactor_service()
    hours_back = req.hours_back if req else 6
    return service.distill_macro_window(hours_back=hours_back)


@router.post(
    "/daily-archive",
    response_model=DailyPreferenceArchiveDTO,
    summary="Synthesize 24-hour long-term facts and preference updates for persistent memory",
)
def synthesize_daily_archive(
    req: SynthesizeDailyArchiveRequestDTO | None = None,
) -> DailyPreferenceArchiveDTO:
    """Consolidate 24-hour macro milestones into persistent facts and user profile preferences."""
    service = get_activity_compactor_service()
    date_str = req.date_str if req else None
    return service.synthesize_daily_archive(date_str=date_str)


@router.get(
    "/slices",
    response_model=list[MicroActivitySliceDTO],
    summary="Get recent 10-minute micro activity slices",
)
def get_recent_slices(
    limit: int = Query(default=20, ge=1, le=100, description="Max slices to return"),
) -> list[MicroActivitySliceDTO]:
    """Retrieve chronologically recent micro activity slices."""
    service = get_activity_compactor_service()
    return service.get_recent_slices(limit=limit)


@router.get(
    "/folds",
    response_model=list[MacroMilestoneFoldDTO],
    summary="Get recent 6-hour macro milestone folds",
)
def get_recent_folds(
    limit: int = Query(default=10, ge=1, le=50, description="Max folds to return"),
) -> list[MacroMilestoneFoldDTO]:
    """Retrieve chronologically recent macro milestone folds."""
    service = get_activity_compactor_service()
    return service.get_recent_folds(limit=limit)


@router.get(
    "/telemetry",
    response_model=CompactorPipelineTelemetryDTO,
    summary="Get pipeline telemetry and token savings statistics",
)
def get_telemetry() -> CompactorPipelineTelemetryDTO:
    """Retrieve real-time compression ratios and estimated LLM tokens saved."""
    service = get_activity_compactor_service()
    return service.get_telemetry()
