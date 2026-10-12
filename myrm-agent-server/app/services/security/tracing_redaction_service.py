"""Service layer for Tracing Sensitive Data Redactor across all execution paths.

[INPUT]
- SanitizeTraceSpanRequest DTO.

[OUTPUT]
- SanitizeTraceSpanResponse DTO.

[POS]
- Server service encapsulating OpenAI-Agents-JS #1970 sensitive data redaction.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.tracing_redaction import (
    ExecutionPathType,
    RedactedTraceSpan,
    TraceSpanInput,
    TracingOptOutMode,
    TracingRedactor,
)

from app.schemas.tracing_redaction import (
    ExecutionPathTypeDto,
    SanitizeTraceSpanRequest,
    SanitizeTraceSpanResponse,
)

logger = logging.getLogger(__name__)


class TracingRedactionService:
    """Service providing sensitive data redaction across success, error, streaming, retry, and resume paths."""

    def __init__(self, redactor: TracingRedactor | None = None) -> None:
        self._redactor = redactor or TracingRedactor()

    def sanitize_span(
        self, request: SanitizeTraceSpanRequest
    ) -> SanitizeTraceSpanResponse:
        """Sanitize an execution trace span ensuring secret exclusion and opt-out compliance."""
        span_input = TraceSpanInput(
            trace_id=request.trace_id,
            span_id=request.span_id,
            path_type=ExecutionPathType(request.path_type.value),
            payload=request.payload,
            raw_error=request.raw_error,
            opt_out_requested=request.opt_out_requested,
        )

        opt_mode = (
            TracingOptOutMode(request.opt_out_mode.value)
            if request.opt_out_mode
            else None
        )

        res: RedactedTraceSpan = self._redactor.sanitize_span(
            span=span_input,
            opt_out_mode_override=opt_mode,
        )

        return SanitizeTraceSpanResponse(
            trace_id=res.trace_id,
            span_id=res.span_id,
            path_type=ExecutionPathTypeDto(res.path_type.value),
            sanitized_payload=res.sanitized_payload,
            sanitized_error=res.sanitized_error,
            is_dropped=res.is_dropped,
            redaction_count=res.redaction_count,
            policy_applied=res.policy_applied,
        )


_service_instance: TracingRedactionService | None = None


def get_tracing_redaction_service() -> TracingRedactionService:
    """Dependency injector for TracingRedactionService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TracingRedactionService()
    return _service_instance
