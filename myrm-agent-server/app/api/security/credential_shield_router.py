"""API router for Credential Stdin Pipelining & Process Leakage Shield Suite.

[INPUT]
- AnalyzeCommandLineRequest, PipelineCommandRequest, SanitizeDisplayCommandRequest.

[OUTPUT]
- Endpoints for detecting process table secrets, creating stdin pipeline execution specs,
  and generating sanitized command strings for logging.

[POS]
- Server API. Mounted under /api/v1/security/credential-shield.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.credential_shield import (
    AnalyzeCommandLineRequest,
    PipelineCommandRequest,
    PipelinedCommandDto,
    ProcessLeakageAnalysisDto,
    SanitizedDisplayResponse,
    SanitizeDisplayCommandRequest,
)
from app.services.security.credential_shield_service import (
    get_credential_shield_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credential-shield", tags=["credential-shield"])


@router.post("/analyze", response_model=ProcessLeakageAnalysisDto)
def analyze_command_line(request: AnalyzeCommandLineRequest) -> ProcessLeakageAnalysisDto:
    """Analyze a shell command for plain-text credential leaks visible in OS process tables."""
    service = get_credential_shield_service()
    return service.analyze_command(request)


@router.post("/pipeline", response_model=PipelinedCommandDto)
def pipeline_command(request: PipelineCommandRequest) -> PipelinedCommandDto:
    """Transform a command into an immune stdin-pipelined execution specification."""
    service = get_credential_shield_service()
    return service.pipeline_command(request)


@router.post("/sanitize-display", response_model=SanitizedDisplayResponse)
def sanitize_display_command(request: SanitizeDisplayCommandRequest) -> SanitizedDisplayResponse:
    """Redact credentials from a command string for safe logging and UI presentation."""
    service = get_credential_shield_service()
    return service.sanitize_display(request)
