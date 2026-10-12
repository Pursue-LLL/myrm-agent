"""API router for GateGuard invisible Unicode sanitization.

[INPUT]
- SanitizePathRequest, SanitizeReasonRequest, SanitizeDenialPayloadRequest.

[OUTPUT]
- SanitizeResultDto, SanitizeDenialPayloadResponse, GateGuardSanitizePolicySummary.

[POS]
- Security router mounted under /security/gate-guard-sanitizer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.gate_guard_sanitizer import (
    GateGuardSanitizePolicySummary,
    SanitizeDenialPayloadRequest,
    SanitizeDenialPayloadResponse,
    SanitizePathRequest,
    SanitizeReasonRequest,
    SanitizeResultDto,
)
from app.services.security.gate_guard_sanitizer_service import (
    GateGuardSanitizerService,
    get_gate_guard_sanitizer_service,
)

router = APIRouter(
    prefix="/gate-guard-sanitizer", tags=["gate-guard-sanitizer"]
)


@router.post("/sanitize-path", response_model=SanitizeResultDto)
async def sanitize_path(
    request: SanitizePathRequest,
    service: GateGuardSanitizerService = Depends(get_gate_guard_sanitizer_service),
) -> SanitizeResultDto:
    """Sanitize dangerous invisible Unicode in file paths for denial feedback."""
    return service.sanitize_path(request)


@router.post("/sanitize-reason", response_model=SanitizeResultDto)
async def sanitize_reason(
    request: SanitizeReasonRequest,
    service: GateGuardSanitizerService = Depends(get_gate_guard_sanitizer_service),
) -> SanitizeResultDto:
    """Sanitize dangerous invisible Unicode in gate guard denial reasons."""
    return service.sanitize_reason(request)


@router.post("/sanitize-payload", response_model=SanitizeDenialPayloadResponse)
async def sanitize_payload(
    request: SanitizeDenialPayloadRequest,
    service: GateGuardSanitizerService = Depends(get_gate_guard_sanitizer_service),
) -> SanitizeDenialPayloadResponse:
    """Sanitize complete denial event payload (tool name, path, reason)."""
    return service.sanitize_denial_payload(request)


@router.get("/policy", response_model=GateGuardSanitizePolicySummary)
async def get_policy_summary(
    service: GateGuardSanitizerService = Depends(get_gate_guard_sanitizer_service),
) -> GateGuardSanitizePolicySummary:
    """Retrieve active GateGuard Unicode sanitization policy configuration."""
    return service.get_policy_summary()
