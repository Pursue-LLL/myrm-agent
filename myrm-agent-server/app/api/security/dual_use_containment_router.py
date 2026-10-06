"""
[POS] app/api/security/dual_use_containment_router.py
[INPUT] app/schemas/dual_use_containment.py, app/services/security/dual_use_containment_service.py
[OUTPUT] router

FastAPI router for dual-use skill containment and artifact exfiltration shield suite.

Exposes REST endpoints to evaluate skill TTPs, verify execution gates, inspect
artifact egress against data leaks, and retrieve flight recorder audit logs.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.schemas.dual_use_containment import (
    ArtifactEgressEvaluationRequest,
    ArtifactEgressEvaluationResponse,
    DualUseMetricsResponse,
    ExecutionGateCheckRequest,
    ExecutionGateCheckResponse,
    FlightRecorderEntrySchema,
    SkillTtpEvaluationRequest,
    SkillTtpEvaluationResponse,
)
from app.services.security.dual_use_containment_service import (
    DualUseContainmentService,
    get_dual_use_containment_service,
)

router = APIRouter(
    prefix="/dual-use-containment",
    tags=["Dual-Use Skill Containment & Exfiltration Shield"],
)


@router.post(
    "/skills/evaluate-ttp",
    response_model=SkillTtpEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate skill MITRE ATT&CK TTPs and sensitivity level",
)
def evaluate_skill_ttp(
    request: SkillTtpEvaluationRequest,
) -> SkillTtpEvaluationResponse:
    """Analyze a skill for MITRE ATT&CK tactics, dual-use capabilities, and containment rules."""
    service: DualUseContainmentService = get_dual_use_containment_service()
    return service.evaluate_skill_ttp(request)


@router.post(
    "/gate/check-execution",
    response_model=ExecutionGateCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Check skill execution gate authorization and HITL requirement",
)
def check_execution_gate(
    request: ExecutionGateCheckRequest,
) -> ExecutionGateCheckResponse:
    """Verify that dual-use skills are executed within an isolated quarantine pod and authorized by human."""
    service: DualUseContainmentService = get_dual_use_containment_service()
    return service.check_execution_gate(request)


@router.post(
    "/artifacts/evaluate-egress",
    response_model=ArtifactEgressEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect artifact egress to shield against public data leaks",
)
def evaluate_artifact_egress(
    request: ArtifactEgressEvaluationRequest,
) -> ArtifactEgressEvaluationResponse:
    """Detect and block restricted artifacts/screenshots from being uploaded to public untrusted destinations."""
    service: DualUseContainmentService = get_dual_use_containment_service()
    return service.evaluate_artifact_egress(request)


@router.get(
    "/flight-recorder/records",
    response_model=list[FlightRecorderEntrySchema],
    status_code=status.HTTP_200_OK,
    summary="Query security flight recorder audit logs",
)
def get_flight_recorder_records(
    limit: int = Query(default=50, ge=1, le=500, description="Max audit entries to retrieve."),
) -> list[FlightRecorderEntrySchema]:
    """Retrieve immutable audit trail entries from the security flight recorder."""
    service: DualUseContainmentService = get_dual_use_containment_service()
    return service.get_flight_recorder_logs(limit=limit)


@router.get(
    "/metrics",
    response_model=DualUseMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dual-use containment operational metrics",
)
def get_containment_metrics() -> DualUseMetricsResponse:
    """Retrieve telemetry metrics for dual-use skill gating and artifact exfiltration blocks."""
    service: DualUseContainmentService = get_dual_use_containment_service()
    return service.get_metrics()
