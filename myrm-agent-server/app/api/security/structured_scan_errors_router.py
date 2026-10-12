"""API router for Structured JSON Scan Failure Errors.

[INPUT]
- EmitScanFailureRequest, ClassifyScanFailureRequest payloads.

[OUTPUT]
- StructuredScanErrorEnvelopeDto, ClassifiedFailureDto responses.

[POS]
- Security router mounted under /security/structured-scan-errors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.structured_scan_errors import (
    ClassifiedFailureDto,
    ClassifyScanFailureRequest,
    EmitScanFailureRequest,
    StructuredScanErrorEnvelopeDto,
)
from app.services.security.structured_scan_errors_service import (
    StructuredScanErrorsService,
    get_structured_scan_errors_service,
)

router = APIRouter(
    prefix="/structured-scan-errors", tags=["structured-scan-errors"]
)


@router.post("/emit-failure", response_model=StructuredScanErrorEnvelopeDto)
async def emit_scan_failure(
    request: EmitScanFailureRequest,
    service: StructuredScanErrorsService = Depends(
        get_structured_scan_errors_service
    ),
) -> StructuredScanErrorEnvelopeDto:
    """Generate structured JSON error envelope for failed security scan."""
    return service.emit_failure(request)


@router.post("/classify-failure", response_model=ClassifiedFailureDto)
async def classify_scan_failure(
    request: ClassifyScanFailureRequest,
    service: StructuredScanErrorsService = Depends(
        get_structured_scan_errors_service
    ),
) -> ClassifiedFailureDto:
    """Quickly classify raw stderr and exit code into structured error and remediation decision."""
    return service.classify_failure(request)
