"""FastAPI router for Experience Observability Dashboard and Host Plugin Lifecycle (Item 108).

[POS]
app/api/memory/experience_observability_router.py

[INPUT]
- app.schemas.experience_observability, app.services.memory.experience_observability_service

[OUTPUT]
- router (FastAPI APIRouter for Experience Observability and Host Plugin Suite)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.experience_observability import (
    ExperienceObservabilityMetricDTO,
    HostPluginConfigDTO,
    ObservabilityDashboardResponseDTO,
    RecordEffectEventRequest,
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
