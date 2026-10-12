"""
[POS] app/api/security/dual_track_content_audit_router.py
[INPUT] app/schemas/dual_track_content_audit.py, app/services/security/dual_track_content_audit_service.py
[OUTPUT] router

FastAPI router for Decoupled Async Dual-Track Content Audit & Realtime Circuit Breaker Suite.

Exposes REST endpoints to mirror streaming chunks out-of-band, trigger realtime stream circuit-breaking,
perform synchronous compliance scans, and inspect/reset breaker states.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.dual_track_content_audit import (
    BreakerStatusResponse,
    DualTrackMetricsResponse,
    MirrorChunkRequest,
    MirrorChunkResponse,
    ResetBreakerRequest,
    ResetBreakerResponse,
    ScanTextRequest,
    ScanTextResponse,
)
from app.services.security.dual_track_content_audit_service import (
    DualTrackContentAuditService,
    get_dual_track_content_audit_service,
)

router = APIRouter(
    prefix="/dual-track-audit",
    tags=["Dual-Track Content Audit & Stream Circuit Breaker"],
)


@router.post(
    "/mirror-chunk",
    response_model=MirrorChunkResponse,
    status_code=status.HTTP_200_OK,
    summary="Asynchronously mirror stream chunk for out-of-band compliance audit",
)
def mirror_chunk(
    request: MirrorChunkRequest,
) -> MirrorChunkResponse:
    """Mirror streaming token chunk to out-of-band audit queue and check circuit breaker."""
    service: DualTrackContentAuditService = get_dual_track_content_audit_service()
    return service.mirror_chunk(request)


@router.post(
    "/scan-text",
    response_model=ScanTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform synchronous static text compliance audit",
)
def scan_text(
    request: ScanTextRequest,
) -> ScanTextResponse:
    """Deeply inspect full text against trade secrets, credential leaks, and prompt injection."""
    service: DualTrackContentAuditService = get_dual_track_content_audit_service()
    return service.scan_text(request)


@router.get(
    "/sessions/{session_id}/breaker-status",
    response_model=BreakerStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check circuit breaker interruption status for a streaming session",
)
def get_breaker_status(
    session_id: str,
) -> BreakerStatusResponse:
    """Retrieve whether a session's streaming conduit is halted by a safety circuit breaker."""
    service: DualTrackContentAuditService = get_dual_track_content_audit_service()
    return service.get_breaker_status(session_id)


@router.post(
    "/sessions/reset-breaker",
    response_model=ResetBreakerResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset a tripped session circuit breaker",
)
def reset_breaker(
    request: ResetBreakerRequest,
) -> ResetBreakerResponse:
    """Manually clear circuit breaker trip state for an interrupted session."""
    service: DualTrackContentAuditService = get_dual_track_content_audit_service()
    return service.reset_breaker(request)


@router.get(
    "/metrics",
    response_model=DualTrackMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve operational metrics for dual-track out-of-band audit subsystem",
)
def get_metrics() -> DualTrackMetricsResponse:
    """Fetch metrics for mirrored chunks, detected policy violations, and tripped circuit breakers."""
    service: DualTrackContentAuditService = get_dual_track_content_audit_service()
    return service.get_metrics()
