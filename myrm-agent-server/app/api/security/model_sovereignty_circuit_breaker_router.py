"""
[POS] app/api/security/model_sovereignty_circuit_breaker_router.py
[INPUT] fastapi, app.schemas.model_sovereignty_circuit_breaker, app.services.security.model_sovereignty_circuit_breaker_service
[OUTPUT] router

FastAPI router for Model Degradation Circuit Breaker & Sovereign Governance Enclave.
Exposes endpoints for stealth model swap fingerprint inspection, automated fallback routing,
full-stack digital sovereignty audits, and heterogeneous mesh node management.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.schemas.model_sovereignty_circuit_breaker import (
    AuditSovereigntyRequest,
    DegradationCircuitBreakerMetricsResponse,
    HeartbeatResponse,
    InspectTelemetryRequest,
    InspectTelemetryResponse,
    MeshNodeResponse,
    RecordHeartbeatRequest,
    RegisterMeshNodeRequest,
    ResetCircuitRequest,
    ResetCircuitResponse,
    RouteRequestPayload,
    RouteRequestResponse,
    SovereignEnclavePostureResponse,
)
from app.services.security.model_sovereignty_circuit_breaker_service import (
    ModelSovereigntyCircuitBreakerService,
    get_model_sovereignty_circuit_breaker_service,
)

router = APIRouter(
    prefix="/model-sovereignty-circuit-breaker",
    tags=["Model Degradation Circuit Breaker & Sovereign Governance"],
)


@router.post(
    "/inspect-telemetry",
    response_model=InspectTelemetryResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect model inference telemetry to detect stealth degradation or model swaps",
)
def inspect_telemetry(
    request: InspectTelemetryRequest,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> InspectTelemetryResponse:
    """Analyze inference output against baseline fingerprints and update circuit state."""
    return service.inspect_telemetry(request)


@router.post(
    "/route-request",
    response_model=RouteRequestResponse,
    status_code=status.HTTP_200_OK,
    summary="Route model request to primary or fallback target based on circuit state",
)
def route_request(
    payload: RouteRequestPayload,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> RouteRequestResponse:
    """Determine dynamic routing destination taking circuit breaker trip state into account."""
    return service.route_request(payload)


@router.post(
    "/audit-sovereignty",
    response_model=SovereignEnclavePostureResponse,
    status_code=status.HTTP_200_OK,
    summary="Audit self-hosted digital sovereignty across data, models, and execution sandboxes",
)
def audit_sovereignty(
    request: AuditSovereigntyRequest,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> SovereignEnclavePostureResponse:
    """Audit digital autonomy posture and calculate composite sovereignty score."""
    return service.audit_sovereignty(request)


@router.post(
    "/mesh-nodes",
    response_model=MeshNodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Register a compute node in heterogeneous local mesh",
)
def register_mesh_node(
    request: RegisterMeshNodeRequest,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> MeshNodeResponse:
    """Add or update compute node in local mesh."""
    return service.register_mesh_node(request)


@router.post(
    "/mesh-nodes/heartbeat",
    response_model=HeartbeatResponse,
    status_code=status.HTTP_200_OK,
    summary="Record heartbeat signal from a mesh node",
)
def record_heartbeat(
    request: RecordHeartbeatRequest,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> HeartbeatResponse:
    """Update heartbeat timestamp for registered node."""
    return service.record_heartbeat(request)


@router.get(
    "/mesh-nodes/healthy",
    response_model=list[MeshNodeResponse],
    status_code=status.HTTP_200_OK,
    summary="List active healthy compute nodes in local mesh",
)
def list_healthy_nodes(
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> list[MeshNodeResponse]:
    """Retrieve all mesh nodes whose heartbeats are currently active."""
    return service.list_healthy_nodes()


@router.get(
    "/mesh-nodes/best",
    response_model=MeshNodeResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Select optimal available compute node matching preferred type",
)
def get_best_compute_node(
    preferred_type: str = Query("gpu_worker", description="Target node type"),
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> MeshNodeResponse | None:
    """Find highest capacity compute node available."""
    return service.get_best_compute_node(preferred_type)


@router.post(
    "/circuit/reset",
    response_model=ResetCircuitResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually reset circuit breaker for a provider back to CLOSED",
)
def reset_circuit(
    request: ResetCircuitRequest,
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> ResetCircuitResponse:
    """Reset tripped circuit breaker."""
    return service.reset_circuit(request)


@router.get(
    "/metrics",
    response_model=DegradationCircuitBreakerMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative model degradation and sovereignty metrics",
)
def get_metrics(
    service: ModelSovereigntyCircuitBreakerService = Depends(get_model_sovereignty_circuit_breaker_service),
) -> DegradationCircuitBreakerMetricsResponse:
    """Get telemetry inspections, circuit trips, and audit counts."""
    return service.get_metrics()
