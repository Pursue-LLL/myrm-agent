# [POS]: app/api/memory/experience_observability_router.py
# [INPUT]: app.schemas.experience_observability, app.services.memory.experience_observability_service
# [OUTPUT]: router (FastAPI APIRouter for Experience Observability and Host Plugin Suite)

"""FastAPI router for Experience Observability Dashboard and Host Plugin Lifecycle (Item 108)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.experience_observability import (
    ExperienceObservabilityMetricDTO,
    HostPluginConfigDTO,
    ObservabilityDashboardResponseDTO,
    RecordEffectEventRequest,
    RecordRecallEventRequest,
    SessionTraceEvidenceDTO,
    UpdatePluginConfigRequest,
)
from app.services.memory.experience_observability_service import (
    ExperienceObservabilityService,
    get_experience_observability_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experience-observability", tags=["Experience Observability Suite"])


@router.get(
    "/dashboard",
    response_model=ObservabilityDashboardResponseDTO,
    summary="Retrieve full experience observability dashboard triad view",
)
async def get_dashboard(
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> ObservabilityDashboardResponseDTO:
    """Return dashboard aggregating experience items, effect distribution, and host plugin state."""
    return service.get_dashboard()


@router.get(
    "/metrics",
    response_model=list[ExperienceObservabilityMetricDTO],
    summary="List tracked experience telemetry metrics",
)
async def list_metrics(
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
    channel: str | None = Query(default=None, description="Filter by access channel (plugin/mcp/skill)"),
    status: str | None = Query(default=None, description="Filter by effect status (effective/neutral/adverse)"),
) -> list[ExperienceObservabilityMetricDTO]:
    """List experience telemetry metrics with optional channel and status filtering."""
    return service.list_metrics(channel_str=channel, status_str=status)


@router.get(
    "/metrics/{entry_id}",
    response_model=ExperienceObservabilityMetricDTO,
    summary="Get single experience telemetry metric by entry ID",
)
async def get_metric(
    entry_id: str,
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> ExperienceObservabilityMetricDTO:
    """Retrieve telemetry metrics for an individual experience item."""
    metric = service.get_metric(entry_id)
    if metric is None:
        raise HTTPException(status_code=404, detail=f"Experience metric not found: {entry_id}")
    return metric


@router.get(
    "/traces/{session_id}",
    response_model=SessionTraceEvidenceDTO,
    summary="Retrieve originating session trace evidence for an experience",
)
async def get_trace_evidence(
    session_id: str,
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> SessionTraceEvidenceDTO:
    """Retrieve originating session trace evidence linking experience to source context."""
    trace = service.get_trace_evidence(session_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Session trace evidence not found: {session_id}")
    return trace


@router.get(
    "/config",
    response_model=HostPluginConfigDTO,
    summary="Get current zero-refactor host plugin configuration",
)
async def get_plugin_config(
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> HostPluginConfigDTO:
    """Retrieve active host plugin configuration parameters."""
    return service.get_plugin_config()


@router.post(
    "/config",
    response_model=HostPluginConfigDTO,
    summary="Update zero-refactor host plugin configuration",
)
async def update_plugin_config(
    request: UpdatePluginConfigRequest,
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> HostPluginConfigDTO:
    """Update runtime settings for the zero-refactor host plugin."""
    return service.update_plugin_config(request)


@router.post(
    "/record-recall",
    response_model=ExperienceObservabilityMetricDTO,
    summary="Record an experience recall event hit",
)
async def record_recall(
    request: RecordRecallEventRequest,
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> ExperienceObservabilityMetricDTO:
    """Record an experience recall event and update its access metrics."""
    return service.record_recall_event(request)


@router.post(
    "/record-effect",
    response_model=ExperienceObservabilityMetricDTO,
    summary="Record task outcome following experience injection",
)
async def record_effect(
    request: RecordEffectEventRequest,
    service: Annotated[ExperienceObservabilityService, Depends(get_experience_observability_service)],
) -> ExperienceObservabilityMetricDTO:
    """Record task completion or dispute outcome and update success rate distribution."""
    return service.record_effect_event(request)
