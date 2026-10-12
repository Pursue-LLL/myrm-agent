"""
[POS] app/api/security/execution_approval_sanitizer_router.py
[INPUT] fastapi, app.schemas.execution_approval_sanitizer, app.services.security.execution_approval_sanitizer_service
[OUTPUT] execution_approval_sanitizer_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.execution_approval_sanitizer import (
    ApprovalSanitizeRequestDTO,
    ApprovalSanitizeResponseDTO,
    QuickSanitizeRequestDTO,
    QuickSanitizeResponseDTO,
    SanitizerMetricsResponseDTO,
)
from app.services.security.execution_approval_sanitizer_service import (
    ExecutionApprovalSanitizerService,
    get_execution_approval_sanitizer_service,
)

router = APIRouter(
    prefix="/execution-approval-sanitizer",
    tags=["Execution Approval Secret Redaction & Sanitizer"],
)


@router.post(
    "/sanitize",
    response_model=ApprovalSanitizeResponseDTO,
    summary="Sanitize command payload for execution approval",
)
def sanitize_approval_payload(
    request: ApprovalSanitizeRequestDTO,
    service: ExecutionApprovalSanitizerService = Depends(
        get_execution_approval_sanitizer_service
    ),
) -> ApprovalSanitizeResponseDTO:
    """Mask recognizable API keys, tokens, and credentials in command text before presenting in WebUI or IM."""
    return service.sanitize_approval_payload(request)


@router.post(
    "/quick-sanitize",
    response_model=QuickSanitizeResponseDTO,
    summary="Quickly sanitize raw text string",
)
def quick_sanitize_text(
    request: QuickSanitizeRequestDTO,
    service: ExecutionApprovalSanitizerService = Depends(
        get_execution_approval_sanitizer_service
    ),
) -> QuickSanitizeResponseDTO:
    """Quickly redact sensitive credentials from a string."""
    return service.quick_sanitize_text(request)


@router.get(
    "/metrics",
    response_model=SanitizerMetricsResponseDTO,
    summary="Get operational metrics",
)
def get_metrics(
    service: ExecutionApprovalSanitizerService = Depends(
        get_execution_approval_sanitizer_service
    ),
) -> SanitizerMetricsResponseDTO:
    """Fetch cumulative metric counters for sanitized approval payloads."""
    return service.get_metrics()
