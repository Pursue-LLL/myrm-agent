"""
[POS] app/api/security/tool_result_seam_screening_router.py
[INPUT] app/schemas/tool_result_seam_screening.py, app/services/security/tool_result_seam_screening_service.py
[OUTPUT] router

FastAPI router for tool result seam screening and in-place redactor suite.

Exposes REST endpoints to inspect and sanitize tool outputs before context injection.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.tool_result_seam_screening import (
    BatchToolResultScreenRequest,
    BatchToolResultScreenResponse,
    ScreeningPolicyUpdateRequest,
    SeamScreeningMetricsResponse,
    ToolResultScreenRequest,
    ToolResultScreenResponse,
)
from app.services.security.tool_result_seam_screening_service import (
    ToolResultSeamScreeningService,
    get_tool_result_seam_screening_service,
)

router = APIRouter(
    prefix="/tool-result-screening",
    tags=["Tool Result Seam Screening"],
)


@router.post(
    "/screen",
    response_model=ToolResultScreenResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen and sanitize tool output at seam",
)
def screen_tool_result(
    request: ToolResultScreenRequest,
) -> ToolResultScreenResponse:
    """Perform physical seam screening and in-place redaction on a single tool output."""
    service: ToolResultSeamScreeningService = get_tool_result_seam_screening_service()
    return service.screen_tool_result(request)


@router.post(
    "/batch-screen",
    response_model=BatchToolResultScreenResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch screen tool outputs",
)
def batch_screen_tool_results(
    request: BatchToolResultScreenRequest,
) -> BatchToolResultScreenResponse:
    """Batch screen multiple tool results at the execution seam."""
    service: ToolResultSeamScreeningService = get_tool_result_seam_screening_service()
    return service.batch_screen(request)


@router.get(
    "/metrics",
    response_model=SeamScreeningMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get seam screening operational metrics",
)
def get_screening_metrics() -> SeamScreeningMetricsResponse:
    """Retrieve operational telemetry and detection statistics."""
    service: ToolResultSeamScreeningService = get_tool_result_seam_screening_service()
    return service.get_metrics()


@router.post(
    "/policy",
    status_code=status.HTTP_200_OK,
    summary="Update screening policy",
)
def update_screening_policy(
    request: ScreeningPolicyUpdateRequest,
) -> dict[str, str]:
    """Dynamically configure seam screening thresholds and parameters."""
    service: ToolResultSeamScreeningService = get_tool_result_seam_screening_service()
    service.update_policy(request)
    return {"status": "policy_updated", "detail": "Seam screening policy reconfigured successfully"}
