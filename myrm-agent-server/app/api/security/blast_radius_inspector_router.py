"""API Router for Agent Blast Radius Static Inspector and Action Surface Guard Attribution.

[POS] app/api/security/blast_radius_inspector_router.py
[INPUT] fastapi, app.schemas.blast_radius_inspector, app.services.security.blast_radius_inspector_service
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.blast_radius_inspector import (
    ActionSurfaceExposureReportDTO,
    ActionSurfaceInspectRequest,
    AutoRepairPatchRequest,
    AutoRepairPatchResponse,
    GuardAttributionRequest,
    GuardAttributionResponse,
    KillSwitchStatusResponse,
    ToggleKillSwitchRequest,
)
from app.services.security.blast_radius_inspector_service import (
    BlastRadiusInspectorService,
    get_blast_radius_service,
)

router = APIRouter(
    prefix="/blast-radius",
    tags=["Security - Agent Blast Radius Static Inspector & Guard Attribution"],
)


@router.post(
    "/inspect-profile",
    response_model=ActionSurfaceExposureReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Statically inspect agent profile action surface",
)
def inspect_profile_endpoint(
    request: ActionSurfaceInspectRequest,
    service: BlastRadiusInspectorService = Depends(get_blast_radius_service),
) -> ActionSurfaceExposureReportDTO:
    """Statically compute 4D action surface, multi-tier danger posture, and pre-admission posture."""
    return service.inspect_action_surface(request)


@router.post(
    "/guard-attribution",
    response_model=GuardAttributionResponse,
    status_code=status.HTTP_200_OK,
    summary="Compute guard attribution matrix and downgraded risk tiers",
)
def guard_attribution_endpoint(
    request: GuardAttributionRequest,
    service: BlastRadiusInspectorService = Depends(get_blast_radius_service),
) -> GuardAttributionResponse:
    """Correlate configured guardrails with action surface sinks."""
    return service.attribute_guards(request)


@router.post(
    "/auto-repair",
    response_model=AutoRepairPatchResponse,
    status_code=status.HTTP_200_OK,
    summary="Synthesize auto-repair least-privilege policy patches",
)
def auto_repair_endpoint(
    request: AutoRepairPatchRequest,
    service: BlastRadiusInspectorService = Depends(get_blast_radius_service),
) -> AutoRepairPatchResponse:
    """Synthesize least-privilege policy patch proposals for unmitigated sinks."""
    return service.synthesize_auto_repairs(request)


@router.post(
    "/kill-switch/toggle",
    response_model=KillSwitchStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Trip or reset global outgoing action kill switch",
)
def toggle_kill_switch_endpoint(
    request: ToggleKillSwitchRequest,
    service: BlastRadiusInspectorService = Depends(get_blast_radius_service),
) -> KillSwitchStatusResponse:
    """Trip or reset emergency kill switch halting all outbound network/send actions."""
    return service.toggle_kill_switch(request)


@router.get(
    "/kill-switch/status",
    response_model=KillSwitchStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve current state of global action kill switch",
)
def get_kill_switch_status_endpoint(
    service: BlastRadiusInspectorService = Depends(get_blast_radius_service),
) -> KillSwitchStatusResponse:
    """Query current trip status and operator metadata for the kill switch."""
    return service.get_kill_switch_status()
