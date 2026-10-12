"""FastAPI router for Tracing Sensitive Data Redactor across all execution paths.

[INPUT]
- SanitizeTraceSpanRequest JSON payloads.

[OUTPUT]
- SanitizeTraceSpanResponse JSON payloads and opt-out mode configurations.

[POS]
- REST API layer exposing OpenAI-Agents-JS #1970 sensitive data redaction.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.schemas.tracing_redaction import (
    ExecutionPathTypeDto,
    SanitizeTraceSpanRequest,
    SanitizeTraceSpanResponse,
    TracingOptOutModeDto,
)
from app.services.security.tracing_redaction_service import (
    TracingRedactionService,
    get_tracing_redaction_service,
)

router = APIRouter(
    prefix="/tracing-redaction",
    tags=["Security: Tracing Redaction"],
)


class TracingOptOutModesResponse(BaseModel):
    """Supported opt-out modes and execution paths."""

    available_opt_out_modes: list[str] = Field(
        description="Supported opt-out modes for telemetry traces"
    )
    supported_execution_paths: list[str] = Field(
        description="All execution path categories supported for redaction"
    )


@router.post(
    "/sanitize-span",
    response_model=SanitizeTraceSpanResponse,
    summary="Sanitize sensitive data in a telemetry trace span across execution paths",
)
def sanitize_trace_span(
    request: SanitizeTraceSpanRequest,
    service: TracingRedactionService = Depends(get_tracing_redaction_service),
) -> SanitizeTraceSpanResponse:
    """Sanitize execution span ensuring secrets exclusion across success, error, streaming, retry, and resume."""
    return service.sanitize_span(request)


@router.get(
    "/opt-out-modes",
    response_model=TracingOptOutModesResponse,
    summary="Get available opt-out modes and supported execution paths",
)
def get_opt_out_modes() -> TracingOptOutModesResponse:
    """Return all available opt-out handling modes and execution path types."""
    return TracingOptOutModesResponse(
        available_opt_out_modes=[m.value for m in TracingOptOutModeDto],
        supported_execution_paths=[p.value for p in ExecutionPathTypeDto],
    )
